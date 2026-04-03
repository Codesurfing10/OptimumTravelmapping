"""
NOAA Weather API client (api.weather.gov).

Provides grid-based weather forecast data for US coastal and ocean areas.
No API key is required, but a descriptive User-Agent is mandatory per NOAA policy.

Endpoints used:
  /points/{lat},{lon}          → resolve lat/lon to a WFO grid cell
  /gridpoints/{wfo}/{x},{y}    → raw gridpoint data (wind, precipitation, etc.)
  /gridpoints/{wfo}/{x},{y}/forecast/hourly  → human-readable hourly forecast
"""

import logging
from typing import Optional

import requests
from cachetools import TTLCache

logger = logging.getLogger(__name__)

WEATHER_API = 'https://api.weather.gov'
REQUEST_TIMEOUT = 20

_points_cache: TTLCache = TTLCache(maxsize=500, ttl=86400)   # 24 h — grid cells rarely change
_forecast_cache: TTLCache = TTLCache(maxsize=500, ttl=3600)  # 1 h


def _headers(user_agent: str) -> dict:
    return {
        'User-Agent': user_agent,
        'Accept': 'application/geo+json',
    }


def _get_json(url: str, user_agent: str) -> Optional[dict]:
    try:
        resp = requests.get(url, timeout=REQUEST_TIMEOUT, headers=_headers(user_agent))
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as exc:
        logger.warning('NOAA Weather API request failed for %s: %s', url, exc)
        return None


# ---------------------------------------------------------------------------
# Grid point resolution
# ---------------------------------------------------------------------------

def get_grid_point(lat: float, lon: float, user_agent: str) -> Optional[dict]:
    """
    Resolve a lat/lon to a NOAA WFO grid point.
    Returns dict with keys: wfo, gridX, gridY, forecastUrl, forecastHourlyUrl,
    forecastGridDataUrl, city, state.
    Only works for coordinates within the US NWS coverage area (including US waters).
    """
    key = f'{lat:.4f},{lon:.4f}'
    if key in _points_cache:
        return _points_cache[key]

    url = f'{WEATHER_API}/points/{lat:.4f},{lon:.4f}'
    data = _get_json(url, user_agent)
    if not data or 'properties' not in data:
        return None

    props = data['properties']
    result = {
        'wfo': props.get('cwa'),
        'gridX': props.get('gridX'),
        'gridY': props.get('gridY'),
        'forecast_url': props.get('forecast'),
        'forecast_hourly_url': props.get('forecastHourly'),
        'forecast_grid_url': props.get('forecastGridData'),
        'city': props.get('relativeLocation', {}).get('properties', {}).get('city'),
        'state': props.get('relativeLocation', {}).get('properties', {}).get('state'),
        'timezone': props.get('timeZone'),
    }
    _points_cache[key] = result
    return result


# ---------------------------------------------------------------------------
# Forecast retrieval
# ---------------------------------------------------------------------------

def get_forecast(lat: float, lon: float, user_agent: str,
                 hourly: bool = False) -> Optional[dict]:
    """
    Return a structured weather forecast for the given coordinates.
    Falls back to None if outside NOAA coverage.

    Returns dict with:
      - location: {city, state, lat, lon}
      - periods: list of forecast periods with weather details
      - summary: condensed summary of conditions
    """
    cache_key = f'{lat:.4f},{lon:.4f}:{"h" if hourly else "d"}'
    if cache_key in _forecast_cache:
        return _forecast_cache[cache_key]

    grid = get_grid_point(lat, lon, user_agent)
    if not grid:
        return None

    forecast_url = grid['forecast_hourly_url'] if hourly else grid['forecast_url']
    if not forecast_url:
        return None

    data = _get_json(forecast_url, user_agent)
    if not data or 'properties' not in data:
        return None

    periods_raw = data['properties'].get('periods', [])
    periods = []
    for p in periods_raw[:12]:  # limit to 12 periods
        periods.append({
            'name': p.get('name'),
            'start': p.get('startTime'),
            'end': p.get('endTime'),
            'is_daytime': p.get('isDaytime', True),
            'temp_f': p.get('temperature'),
            'temp_unit': p.get('temperatureUnit', 'F'),
            'wind_speed': p.get('windSpeed'),
            'wind_dir': p.get('windDirection'),
            'icon': p.get('icon'),
            'short_forecast': p.get('shortForecast'),
            'detailed_forecast': p.get('detailedForecast'),
            'precipitation_pct': p.get('probabilityOfPrecipitation', {}).get('value'),
        })

    result = {
        'location': {
            'city': grid.get('city'),
            'state': grid.get('state'),
            'lat': lat,
            'lon': lon,
            'timezone': grid.get('timezone'),
        },
        'periods': periods,
        'summary': _summarize_forecast(periods),
    }
    _forecast_cache[cache_key] = result
    return result


def get_grid_conditions(lat: float, lon: float, user_agent: str) -> Optional[dict]:
    """
    Fetch raw gridpoint data and extract marine-relevant parameters:
    wind speed, wind direction, wave height, precipitation probability.
    Returns a simplified conditions dict suitable for route scoring.
    """
    cache_key = f'grid:{lat:.4f},{lon:.4f}'
    if cache_key in _forecast_cache:
        return _forecast_cache[cache_key]

    grid = get_grid_point(lat, lon, user_agent)
    if not grid or not grid.get('forecast_grid_url'):
        return None

    data = _get_json(grid['forecast_grid_url'], user_agent)
    if not data or 'properties' not in data:
        return None

    props = data['properties']

    def first_value(key: str) -> Optional[float]:
        """Extract the first value from a NOAA gridpoint quantity series."""
        series = props.get(key, {}).get('values', [])
        if not series:
            return None
        try:
            return float(series[0].get('value'))
        except (TypeError, ValueError):
            return None

    wind_speed_kmh = first_value('windSpeed')
    wind_speed_ms = wind_speed_kmh / 3.6 if wind_speed_kmh is not None else None
    precip_pct = first_value('probabilityOfPrecipitation')
    wave_height_m = first_value('waveHeight')
    swell_height_m = first_value('primarySwellHeight')

    conditions = {
        'lat': lat,
        'lon': lon,
        'wind_speed_ms': wind_speed_ms,
        'wind_speed_kmh': wind_speed_kmh,
        'precip_probability_pct': precip_pct,
        'wave_height_m': wave_height_m,
        'swell_height_m': swell_height_m,
        'source': 'noaa_grid',
    }
    _forecast_cache[cache_key] = conditions
    return conditions


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _summarize_forecast(periods: list[dict]) -> dict:
    """Build a brief summary dict from the first available forecast period."""
    if not periods:
        return {}
    first = periods[0]
    rain_periods = [p for p in periods[:6] if p.get('precipitation_pct') is not None
                    and p['precipitation_pct'] > 30]
    return {
        'current_short': first.get('short_forecast'),
        'wind': first.get('wind_speed'),
        'wind_dir': first.get('wind_dir'),
        'temp_f': first.get('temp_f'),
        'rain_likely': len(rain_periods) > 0,
        'rain_periods': len(rain_periods),
    }
