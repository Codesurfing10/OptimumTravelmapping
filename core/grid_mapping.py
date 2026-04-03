"""
Geospatial grid mapping utilities.

Handles:
  - Great-circle intermediate waypoint generation
  - Bounding-box grid creation around a route
  - Coordinate distance calculations (Haversine)
  - Wave/weather condition scoring for route cells
"""

import math
from typing import Optional

EARTH_RADIUS_KM = 6371.0


# ---------------------------------------------------------------------------
# Distance and bearing
# ---------------------------------------------------------------------------

def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return the great-circle distance in km between two lat/lon points."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def initial_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return the initial bearing (degrees, 0–360) from point 1 to point 2."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dlambda = math.radians(lon2 - lon1)
    x = math.sin(dlambda) * math.cos(phi2)
    y = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlambda)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def destination_point(lat: float, lon: float,
                      bearing_deg: float, distance_km: float) -> tuple[float, float]:
    """
    Return the lat/lon of a point reached by travelling distance_km along
    bearing_deg from (lat, lon).
    """
    d_r = distance_km / EARTH_RADIUS_KM
    phi1 = math.radians(lat)
    lambda1 = math.radians(lon)
    theta = math.radians(bearing_deg)

    phi2 = math.asin(
        math.sin(phi1) * math.cos(d_r)
        + math.cos(phi1) * math.sin(d_r) * math.cos(theta)
    )
    lambda2 = lambda1 + math.atan2(
        math.sin(theta) * math.sin(d_r) * math.cos(phi1),
        math.cos(d_r) - math.sin(phi1) * math.sin(phi2)
    )
    return math.degrees(phi2), (math.degrees(lambda2) + 540) % 360 - 180


# ---------------------------------------------------------------------------
# Waypoint interpolation
# ---------------------------------------------------------------------------

def interpolate_waypoints(start: tuple[float, float], end: tuple[float, float],
                           n_points: int = 10) -> list[tuple[float, float]]:
    """
    Return n_points intermediate points along the great-circle path from
    start to end (both as (lat, lon) tuples), inclusive of start and end.
    """
    if n_points < 2:
        return [start, end]

    lat1, lon1 = start
    lat2, lon2 = end
    total_km = haversine_km(lat1, lon1, lat2, lon2)
    bearing = initial_bearing(lat1, lon1, lat2, lon2)

    points = []
    for i in range(n_points):
        fraction = i / (n_points - 1)
        dist = fraction * total_km
        pt = destination_point(lat1, lon1, bearing, dist)
        points.append(pt)
    return points


def create_route_grid(start: tuple[float, float], end: tuple[float, float],
                      n_waypoints: int = 10, n_offsets: int = 5,
                      max_offset_km: float = 200.0) -> list[list[tuple[float, float]]]:
    """
    Create a 2D grid of candidate waypoints around the straight-line route.

    Returns a list of 'lanes' — each lane is a list of (lat, lon) waypoints
    running from start to end.  The centre lane (index n_offsets//2) follows
    the direct great-circle route; outer lanes are offset laterally.

    Args:
        start: (lat, lon) origin
        end:   (lat, lon) destination
        n_waypoints: points per lane along the route
        n_offsets:   number of lateral lanes (odd number recommended)
        max_offset_km: total lateral spread in km (split equally across lanes)
    """
    bearing = initial_bearing(*start, *end)
    port_bearing = (bearing - 90) % 360   # left of route
    stbd_bearing = (bearing + 90) % 360   # right of route

    # Offsets: symmetric around 0 (negative = port, positive = starboard)
    half = n_offsets // 2
    offset_kms = [
        (i - half) * (max_offset_km / max(half, 1))
        for i in range(n_offsets)
    ]

    lanes = []
    for offset_km in offset_kms:
        if offset_km == 0:
            lanes.append(interpolate_waypoints(start, end, n_waypoints))
            continue
        side_bearing = stbd_bearing if offset_km > 0 else port_bearing
        abs_offset = abs(offset_km)
        # Shift start and end laterally, then interpolate between them
        shifted_start = destination_point(*start, side_bearing, abs_offset)
        shifted_end = destination_point(*end, side_bearing, abs_offset)
        lanes.append(interpolate_waypoints(shifted_start, shifted_end, n_waypoints))

    return lanes


# ---------------------------------------------------------------------------
# Condition scoring
# ---------------------------------------------------------------------------

def score_conditions(wind_speed_ms: Optional[float] = None,
                     wave_height_m: Optional[float] = None,
                     precip_pct: Optional[float] = None,
                     swell_height_m: Optional[float] = None) -> float:
    """
    Return a 0–10 composite danger score for a waypoint.

    Scoring weights:
      Wind speed  : 35 %  (storm threshold ≈ 24.5 m/s)
      Wave height : 40 %  (phenomenal threshold ≈ 14 m)
      Precipitation: 15 % (100 % probability ≈ max contribution)
      Swell height: 10 %  (threshold ≈ 8 m)
    """
    score = 0.0
    if wind_speed_ms is not None:
        score += min(wind_speed_ms / 24.5, 1.0) * 3.5
    if wave_height_m is not None:
        score += min(wave_height_m / 14.0, 1.0) * 4.0
    if precip_pct is not None:
        score += min(precip_pct / 100.0, 1.0) * 1.5
    if swell_height_m is not None:
        score += min(swell_height_m / 8.0, 1.0) * 1.0
    return round(score, 3)


def condition_colour(danger_score: float) -> str:
    """Map a danger score to a CSS-safe hex colour for map visualisation."""
    if danger_score < 2.0:
        return '#2ecc71'   # green — calm
    if danger_score < 4.0:
        return '#f1c40f'   # yellow — light/moderate
    if danger_score < 6.0:
        return '#e67e22'   # orange — rough
    if danger_score < 8.0:
        return '#e74c3c'   # red — very rough
    return '#8e44ad'       # purple — storm


def condition_label(danger_score: float) -> str:
    """Return a human-readable sea-state label for a danger score."""
    if danger_score < 2.0:
        return 'Calm'
    if danger_score < 4.0:
        return 'Moderate'
    if danger_score < 6.0:
        return 'Rough'
    if danger_score < 8.0:
        return 'Very Rough / Gale'
    return 'Storm / Extreme'


# ---------------------------------------------------------------------------
# Bounding box helpers
# ---------------------------------------------------------------------------

def bounding_box(points: list[tuple[float, float]],
                 padding_deg: float = 1.0) -> dict:
    """Return a bounding box dict for a list of (lat, lon) points."""
    lats = [p[0] for p in points]
    lons = [p[1] for p in points]
    return {
        'min_lat': min(lats) - padding_deg,
        'max_lat': max(lats) + padding_deg,
        'min_lon': min(lons) - padding_deg,
        'max_lon': max(lons) + padding_deg,
    }
