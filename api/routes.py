"""
Flask REST API routes for OptimumTravelMapping.
"""

import logging
from functools import wraps

from flask import Blueprint, current_app, jsonify, request

from api import noaa_ndbc, noaa_weather
from core.route_optimizer import optimize_route

logger = logging.getLogger(__name__)
api_bp = Blueprint('api', __name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _user_agent() -> str:
    return current_app.config.get('NOAA_USER_AGENT',
                                  'OptimumTravelMapping/1.0')


def _json_error(message: str, status: int = 400):
    return jsonify({'error': message}), status


def require_params(*params):
    """Decorator: validate that all listed query-string params are present."""
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            missing = [p for p in params if request.args.get(p) is None]
            if missing:
                return _json_error(f"Missing required parameters: {', '.join(missing)}")
            return fn(*args, **kwargs)
        return wrapper
    return decorator


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@api_bp.route('/health')
def health():
    return jsonify({'status': 'ok', 'service': 'OptimumTravelMapping API'})


# ---------------------------------------------------------------------------
# Buoys
# ---------------------------------------------------------------------------

@api_bp.route('/buoys')
def list_buoys():
    """
    GET /api/buoys
    Return list of active NDBC stations with lat/lon.
    Optional query params: lat, lon, radius_km — filter to a bounding area.
    """
    stations = noaa_ndbc.get_active_buoys()

    lat = request.args.get('lat', type=float)
    lon = request.args.get('lon', type=float)
    radius_km = request.args.get('radius_km', type=float)

    if lat is not None and lon is not None and radius_km:
        from core.grid_mapping import haversine_km
        stations = [
            s for s in stations
            if haversine_km(lat, lon, s['lat'], s['lon']) <= radius_km
        ]

    return jsonify({'count': len(stations), 'buoys': stations})


@api_bp.route('/buoys/observations')
def latest_observations():
    """
    GET /api/buoys/observations
    Return latest observations for all NDBC buoys (bulk).
    Optional: lat, lon, radius_km to filter.
    """
    obs = noaa_ndbc.get_latest_observations()

    lat = request.args.get('lat', type=float)
    lon = request.args.get('lon', type=float)
    radius_km = request.args.get('radius_km', type=float)

    if lat is not None and lon is not None and radius_km:
        from core.grid_mapping import haversine_km
        obs = {
            sid: o for sid, o in obs.items()
            if haversine_km(lat, lon, o['lat'], o['lon']) <= radius_km
        }

    buoys_list = list(obs.values())
    # Build GeoJSON FeatureCollection for easy map rendering
    features = []
    for b in buoys_list:
        features.append({
            'type': 'Feature',
            'geometry': {
                'type': 'Point',
                'coordinates': [b['lon'], b['lat']],
            },
            'properties': b,
        })

    return jsonify({
        'type': 'FeatureCollection',
        'count': len(features),
        'features': features,
    })


@api_bp.route('/buoys/<station_id>')
def buoy_detail(station_id: str):
    """
    GET /api/buoys/<station_id>
    Return the latest observation for a single NDBC station.
    """
    obs = noaa_ndbc.get_buoy_observations(station_id.upper())
    if obs is None:
        return _json_error(f'No data found for station {station_id}', 404)
    return jsonify(obs)


# ---------------------------------------------------------------------------
# Weather
# ---------------------------------------------------------------------------

@api_bp.route('/weather')
@require_params('lat', 'lon')
def weather():
    """
    GET /api/weather?lat=<lat>&lon=<lon>[&hourly=1]
    Return NOAA gridpoint forecast for the given coordinates.
    Only available for coordinates within NOAA NWS coverage (US and US waters).
    """
    lat = request.args.get('lat', type=float)
    lon = request.args.get('lon', type=float)
    hourly = request.args.get('hourly', '0') == '1'

    forecast = noaa_weather.get_forecast(lat, lon, _user_agent(), hourly=hourly)
    if forecast is None:
        return _json_error(
            'No NOAA forecast available for this location '
            '(outside NWS coverage area or API unavailable)', 404
        )
    return jsonify(forecast)


@api_bp.route('/weather/grid')
@require_params('lat', 'lon')
def weather_grid():
    """
    GET /api/weather/grid?lat=<lat>&lon=<lon>
    Return raw NOAA gridpoint conditions (wind, wave, precipitation) for scoring.
    """
    lat = request.args.get('lat', type=float)
    lon = request.args.get('lon', type=float)

    conditions = noaa_weather.get_grid_conditions(lat, lon, _user_agent())
    if conditions is None:
        return _json_error('Grid data not available for this location', 404)
    return jsonify(conditions)


# ---------------------------------------------------------------------------
# Route optimisation
# ---------------------------------------------------------------------------

@api_bp.route('/route/optimize', methods=['POST'])
def route_optimize():
    """
    POST /api/route/optimize
    Body (JSON):
      {
        "start": {"lat": 25.0, "lon": -80.0},
        "end":   {"lat": 40.0, "lon": -65.0},
        "waypoints": 12,   // optional, default 12
        "lanes": 5         // optional, default 5
      }

    Returns a GeoJSON FeatureCollection with optimal and direct routes plus
    per-waypoint weather/danger data.
    """
    body = request.get_json(silent=True)
    if not body:
        return _json_error('Request body must be JSON')

    try:
        start = body['start']
        end = body['end']
        start_lat, start_lon = float(start['lat']), float(start['lon'])
        end_lat, end_lon = float(end['lat']), float(end['lon'])
    except (KeyError, TypeError, ValueError):
        return _json_error('start and end must contain numeric lat/lon fields')

    requested_waypoints = int(body.get('waypoints', 12))
    requested_lanes = int(body.get('lanes', 5))
    n_waypoints = min(requested_waypoints, 20)
    n_lanes = min(requested_lanes, 9)
    if n_waypoints < requested_waypoints or n_lanes < requested_lanes:
        logger.warning(
            'Route params capped: waypoints %d→%d, lanes %d→%d',
            requested_waypoints, n_waypoints, requested_lanes, n_lanes,
        )
    ua = _user_agent()

    def weather_fn(lat, lon):
        return noaa_weather.get_grid_conditions(lat, lon, ua)

    # Fetch NDBC bulk observations once (cached) for buoy-based fallback
    ndbc_obs = noaa_ndbc.get_latest_observations()

    try:
        result = optimize_route(
            start_lat, start_lon,
            end_lat, end_lon,
            noaa_weather_fn=weather_fn,
            ndbc_obs=ndbc_obs,
            n_waypoints=n_waypoints,
            n_lanes=n_lanes,
        )
    except Exception:
        logger.exception('Route optimization failed')
        return _json_error('Route optimization failed. Check coordinates and try again.', 500)

    return jsonify(result)
