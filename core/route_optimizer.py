"""
Route optimizer for ocean travel.

Algorithm:
  1. Generate a grid of candidate waypoint lanes around the direct route
     (see core.grid_mapping.create_route_grid).
  2. Fetch NOAA weather / NDBC buoy conditions for each waypoint.
  3. Score each lane by its cumulative danger score.
  4. Return the safest lane as a GeoJSON LineString together with per-waypoint
     weather data.

The optimizer is intentionally lightweight so it can run within a single HTTP
request without timing out on a Render free-tier instance.
"""

import logging
from typing import Optional

from core.grid_mapping import (
    create_route_grid,
    haversine_km,
    score_conditions,
    condition_colour,
    condition_label,
    bounding_box,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def optimize_route(
    start_lat: float, start_lon: float,
    end_lat: float, end_lon: float,
    noaa_weather_fn,          # callable(lat, lon) → conditions dict or None
    ndbc_obs: dict,           # pre-fetched {station_id: obs} from NDBC
    n_waypoints: int = 12,
    n_lanes: int = 5,
    max_offset_km: float = 300.0,
) -> dict:
    """
    Compute the optimum route from (start_lat, start_lon) to (end_lat, end_lon).

    Args:
        noaa_weather_fn : function that accepts (lat, lon) and returns a
                          conditions dict (keys: wind_speed_ms, wave_height_m,
                          precip_probability_pct, swell_height_m) or None.
        ndbc_obs        : latest NDBC observations keyed by station_id, used to
                          enrich nearby waypoints with buoy data.

    Returns a GeoJSON FeatureCollection with:
      - "optimal_route"  Feature (LineString) — the recommended path
      - "direct_route"   Feature (LineString) — the straight-line baseline
      - "waypoints"      Feature list — each waypoint with weather data
      - "summary"        analysis metadata
    """
    start = (start_lat, start_lon)
    end = (end_lat, end_lon)
    total_km = haversine_km(start_lat, start_lon, end_lat, end_lon)

    # Build route grid (list of lanes)
    lanes = create_route_grid(
        start, end,
        n_waypoints=n_waypoints,
        n_offsets=n_lanes,
        max_offset_km=min(max_offset_km, total_km * 0.3),  # cap offset at 30 % of route
    )

    # Score every lane
    lane_results = []
    for lane_idx, lane in enumerate(lanes):
        scored_waypoints = []
        lane_total_score = 0.0

        for wp_lat, wp_lon in lane:
            conditions = _get_conditions_for_point(
                wp_lat, wp_lon, noaa_weather_fn, ndbc_obs
            )
            danger = score_conditions(
                wind_speed_ms=conditions.get('wind_speed_ms'),
                wave_height_m=conditions.get('wave_height_m'),
                precip_pct=conditions.get('precip_probability_pct'),
                swell_height_m=conditions.get('swell_height_m'),
            )
            conditions['danger_score'] = danger
            conditions['colour'] = condition_colour(danger)
            conditions['condition'] = condition_label(danger)
            scored_waypoints.append({
                'lat': wp_lat,
                'lon': wp_lon,
                'conditions': conditions,
            })
            lane_total_score += danger

        lane_results.append({
            'lane_idx': lane_idx,
            'is_direct': lane_idx == n_lanes // 2,
            'waypoints': scored_waypoints,
            'total_score': round(lane_total_score, 3),
            'avg_score': round(lane_total_score / len(lane), 3) if lane else 0,
        })

    # Pick the safest lane
    optimal = min(lane_results, key=lambda l: l['total_score'])
    direct = lane_results[n_lanes // 2]

    # Build GeoJSON output
    optimal_coords = [[w['lon'], w['lat']] for w in optimal['waypoints']]
    direct_coords = [[w['lon'], w['lat']] for w in direct['waypoints']]

    # Waypoint features for the optimal lane
    wp_features = []
    for wp in optimal['waypoints']:
        cond = wp['conditions']
        wp_features.append({
            'type': 'Feature',
            'geometry': {'type': 'Point', 'coordinates': [wp['lon'], wp['lat']]},
            'properties': {
                'danger_score': cond.get('danger_score', 0),
                'condition': cond.get('condition', 'Unknown'),
                'colour': cond.get('colour', '#888'),
                'wind_speed_ms': cond.get('wind_speed_ms'),
                'wave_height_m': cond.get('wave_height_m'),
                'precip_pct': cond.get('precip_probability_pct'),
                'source': cond.get('source', 'estimated'),
                'nearest_buoy': cond.get('nearest_buoy'),
            },
        })

    all_lats = [start_lat, end_lat]
    all_lons = [start_lon, end_lon]
    bbox = bounding_box([(lat, lon) for lat, lon in zip(all_lats, all_lons)])

    summary = {
        'distance_km': round(total_km, 1),
        'direct_avg_danger': direct['avg_score'],
        'optimal_avg_danger': optimal['avg_score'],
        'improvement_pct': round(
            (direct['avg_score'] - optimal['avg_score']) / max(direct['avg_score'], 0.01) * 100,
            1,
        ),
        'optimal_lane_offset': optimal['lane_idx'] - n_lanes // 2,
        'recommendation': _recommendation(optimal['avg_score']),
        'lanes_evaluated': len(lane_results),
        'bounding_box': bbox,
    }

    return {
        'type': 'FeatureCollection',
        'features': [
            {
                'type': 'Feature',
                'id': 'optimal_route',
                'geometry': {'type': 'LineString', 'coordinates': optimal_coords},
                'properties': {
                    'route_type': 'optimal',
                    'avg_danger': optimal['avg_score'],
                    'colour': '#00d4ff',
                },
            },
            {
                'type': 'Feature',
                'id': 'direct_route',
                'geometry': {'type': 'LineString', 'coordinates': direct_coords},
                'properties': {
                    'route_type': 'direct',
                    'avg_danger': direct['avg_score'],
                    'colour': '#e74c3c',
                },
            },
            *wp_features,
        ],
        'summary': summary,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_conditions_for_point(
    lat: float, lon: float,
    noaa_weather_fn,
    ndbc_obs: dict,
    buoy_influence_km: float = 250.0,
) -> dict:
    """
    Build a conditions dict for (lat, lon) by:
      1. Trying the NOAA Weather API (US coverage only).
      2. Interpolating from the nearest NDBC buoy within buoy_influence_km.
      3. Returning an empty dict if neither source is available.
    """
    conditions: dict = {}

    # --- NOAA Weather API ---
    try:
        grid_data = noaa_weather_fn(lat, lon)
        if grid_data:
            conditions.update({
                'wind_speed_ms': grid_data.get('wind_speed_ms'),
                'wave_height_m': grid_data.get('wave_height_m'),
                'precip_probability_pct': grid_data.get('precip_probability_pct'),
                'swell_height_m': grid_data.get('swell_height_m'),
                'source': 'noaa_grid',
            })
            return conditions
    except Exception as exc:
        logger.debug('NOAA grid lookup failed for (%.3f, %.3f): %s', lat, lon, exc)

    # --- NDBC nearest buoy fallback ---
    nearest_buoy, dist_km = _nearest_buoy(lat, lon, ndbc_obs)
    if nearest_buoy and dist_km is not None and dist_km <= buoy_influence_km:
        # Decay influence linearly with distance
        decay = max(0.0, 1.0 - dist_km / buoy_influence_km)
        obs = ndbc_obs[nearest_buoy]

        def scaled(val):
            return round(val * decay, 3) if val is not None else None

        conditions.update({
            'wind_speed_ms': scaled(obs.get('wind_speed_ms')),
            'wave_height_m': scaled(obs.get('wave_height_m')),
            'precip_probability_pct': None,
            'swell_height_m': None,
            'source': 'ndbc_interpolated',
            'nearest_buoy': nearest_buoy,
            'buoy_distance_km': round(dist_km, 1),
        })

    return conditions


def _nearest_buoy(lat: float, lon: float,
                  ndbc_obs: dict) -> tuple[Optional[str], Optional[float]]:
    """Return (station_id, distance_km) for the closest NDBC observation, or (None, None)."""
    best_id = None
    best_dist: Optional[float] = None
    for sid, obs in ndbc_obs.items():
        blat = obs.get('lat')
        blon = obs.get('lon')
        if blat is None or blon is None:
            continue
        d = haversine_km(lat, lon, blat, blon)
        if best_dist is None or d < best_dist:
            best_dist = d
            best_id = sid
    return best_id, best_dist


def _recommendation(avg_danger: float) -> str:
    """Return a travel recommendation string based on average danger score."""
    if avg_danger < 2.0:
        return 'Excellent conditions — safe to travel.'
    if avg_danger < 4.0:
        return 'Moderate conditions — exercise normal caution.'
    if avg_danger < 6.0:
        return 'Rough conditions — experienced mariners only, monitor forecasts.'
    if avg_danger < 8.0:
        return 'Dangerous conditions — travel not recommended.'
    return 'Extreme / storm conditions — do not travel.'
