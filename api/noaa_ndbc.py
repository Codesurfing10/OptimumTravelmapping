"""
NOAA National Data Buoy Center (NDBC) client.

Fetches real-time buoy observations — no authentication required.
Endpoints used:
  - Station list:  https://www.ndbc.noaa.gov/data/stations/station_table.txt
  - Latest obs:    https://www.ndbc.noaa.gov/data/latest_obs/latest_obs.txt
  - Realtime data: https://www.ndbc.noaa.gov/data/realtime2/{station_id}.txt
"""

import logging
import time
from typing import Optional

import requests
from cachetools import TTLCache

logger = logging.getLogger(__name__)

# NOAA NDBC uses these values to denote missing/unavailable data
NDBC_MISSING_VALUES = frozenset({99.0, 999.0, 9999.0})

# Module-level caches
_station_cache: TTLCache = TTLCache(maxsize=1, ttl=3600)
_obs_cache: TTLCache = TTLCache(maxsize=500, ttl=1800)
_latest_cache: TTLCache = TTLCache(maxsize=1, ttl=900)

NDBC_BASE = 'https://www.ndbc.noaa.gov'
REQUEST_TIMEOUT = 15
USER_AGENT = 'OptimumTravelMapping/1.0 (github.com/Codesurfing10)'


def _get(url: str) -> Optional[str]:
    """Perform a GET request, returning text or None on error."""
    try:
        resp = requests.get(url, timeout=REQUEST_TIMEOUT,
                            headers={'User-Agent': USER_AGENT})
        resp.raise_for_status()
        return resp.text
    except requests.RequestException as exc:
        logger.warning('NDBC request failed for %s: %s', url, exc)
        return None


# ---------------------------------------------------------------------------
# Station list
# ---------------------------------------------------------------------------

def get_active_buoys() -> list[dict]:
    """
    Return a list of active NDBC buoy/station dicts with lat/lon.
    Results are cached for 1 hour.
    Format of station_table.txt (pipe-separated):
      #STN  | LAT | LON | ELEV | TZCORR | OWNER | PGRAM | NAME
    """
    if 'stations' in _station_cache:
        return _station_cache['stations']

    url = f'{NDBC_BASE}/data/stations/station_table.txt'
    text = _get(url)
    if not text:
        return []

    stations = []
    lines = text.splitlines()
    for line in lines:
        if line.startswith('#') or not line.strip():
            continue
        parts = [p.strip() for p in line.split('|')]
        if len(parts) < 8:
            continue
        station_id = parts[0]
        try:
            lat = float(parts[1])
            lon = float(parts[2])
        except ValueError:
            continue
        # Filter to ocean/coastal buoys (avoid inland stations far from coast)
        if abs(lat) > 80 or abs(lon) > 180:
            continue
        stations.append({
            'id': station_id,
            'lat': lat,
            'lon': lon,
            'owner': parts[5] if len(parts) > 5 else '',
            'name': parts[7] if len(parts) > 7 else station_id,
        })

    _station_cache['stations'] = stations
    logger.info('Loaded %d NDBC stations', len(stations))
    return stations


# ---------------------------------------------------------------------------
# Latest bulk observations (all stations)
# ---------------------------------------------------------------------------

def get_latest_observations() -> dict[str, dict]:
    """
    Fetch and parse the NDBC latest_obs.txt bulk file.
    Returns a dict keyed by station_id.

    Column order in latest_obs.txt (space-separated):
      #STN LAT LON YY MM DD hh mm WDIR WSPD GST WVHT DPD APD MWD PRES ATMP WTMP DEWP VIS TIDE
    """
    if 'latest' in _latest_cache:
        return _latest_cache['latest']

    url = f'{NDBC_BASE}/data/latest_obs/latest_obs.txt'
    text = _get(url)
    if not text:
        return {}

    result: dict[str, dict] = {}
    lines = text.splitlines()
    for line in lines:
        if line.startswith('#') or not line.strip():
            continue
        cols = line.split()
        if len(cols) < 20:
            continue
        station_id = cols[0]
        obs = _parse_obs_row(station_id, cols)
        if obs:
            result[station_id] = obs

    _latest_cache['latest'] = result
    logger.info('Parsed %d latest buoy observations', len(result))
    return result


def _parse_obs_row(station_id: str, cols: list[str]) -> Optional[dict]:
    """Parse a single row from latest_obs.txt into a structured dict."""
    def safe_float(val: str) -> Optional[float]:
        try:
            f = float(val)
            return None if f in NDBC_MISSING_VALUES else f
        except (ValueError, TypeError):
            return None

    try:
        lat = safe_float(cols[1])
        lon = safe_float(cols[2])
        if lat is None or lon is None:
            return None

        wind_speed = safe_float(cols[9])     # WSPD m/s
        wind_gust = safe_float(cols[10])     # GST m/s
        wind_dir = safe_float(cols[8])       # WDIR degrees
        wave_height = safe_float(cols[11])   # WVHT metres
        wave_period = safe_float(cols[12])   # DPD seconds
        wave_dir = safe_float(cols[14])      # MWD degrees
        pressure = safe_float(cols[15])      # PRES hPa
        air_temp = safe_float(cols[16])      # ATMP °C
        water_temp = safe_float(cols[17])    # WTMP °C

        danger_score = _danger_score(wind_speed, wave_height)
        condition = _condition_label(wind_speed, wave_height)

        return {
            'id': station_id,
            'lat': lat,
            'lon': lon,
            'wind_speed_ms': wind_speed,
            'wind_gust_ms': wind_gust,
            'wind_dir_deg': wind_dir,
            'wave_height_m': wave_height,
            'wave_period_s': wave_period,
            'wave_dir_deg': wave_dir,
            'pressure_hpa': pressure,
            'air_temp_c': air_temp,
            'water_temp_c': water_temp,
            'danger_score': danger_score,
            'condition': condition,
            'timestamp': f"{cols[3]}-{cols[4]}-{cols[5]} {cols[6]}:{cols[7]} UTC"
                         if len(cols) > 7 else None,
        }
    except (IndexError, ValueError) as exc:
        logger.debug('Failed to parse obs row for %s: %s', station_id, exc)
        return None


# ---------------------------------------------------------------------------
# Individual station realtime data
# ---------------------------------------------------------------------------

def get_buoy_observations(station_id: str) -> Optional[dict]:
    """
    Fetch the most recent observation for a single NDBC station.
    Cached per station for 30 minutes.
    """
    key = station_id.upper()
    if key in _obs_cache:
        return _obs_cache[key]

    url = f'{NDBC_BASE}/data/realtime2/{key}.txt'
    text = _get(url)
    if not text:
        return None

    lines = [l for l in text.splitlines() if not l.startswith('#') and l.strip()]
    if not lines:
        return None

    # First two non-comment lines are header rows; data starts at line 3
    data_lines = [l for l in lines if not l.split()[0].startswith('#')]
    if len(data_lines) < 3:
        return None

    # Skip the two header rows (units line included)
    latest = data_lines[2].split()
    headers_line = lines[0].lstrip('#').split()  # YY MM DD hh mm WDIR WSPD ...

    def safe_float(val: str) -> Optional[float]:
        try:
            f = float(val)
            return None if f in NDBC_MISSING_VALUES else f
        except (ValueError, TypeError):
            return None

    # Standard realtime2 column order
    # YY MM DD hh mm | WDIR WSPD GST | WVHT DPD APD MWD | PRES ATMP WTMP DEWP VIS PTDY TIDE
    if len(latest) < 15:
        return None

    wind_speed = safe_float(latest[6])
    wave_height = safe_float(latest[8])
    obs = {
        'id': station_id,
        'timestamp': f"{latest[0]}-{latest[1]}-{latest[2]} {latest[3]}:{latest[4]} UTC",
        'wind_dir_deg': safe_float(latest[5]),
        'wind_speed_ms': wind_speed,
        'wind_gust_ms': safe_float(latest[7]),
        'wave_height_m': wave_height,
        'wave_period_s': safe_float(latest[9]),
        'wave_dir_deg': safe_float(latest[11]) if len(latest) > 11 else None,
        'pressure_hpa': safe_float(latest[12]) if len(latest) > 12 else None,
        'air_temp_c': safe_float(latest[13]) if len(latest) > 13 else None,
        'water_temp_c': safe_float(latest[14]) if len(latest) > 14 else None,
        'danger_score': _danger_score(wind_speed, wave_height),
        'condition': _condition_label(wind_speed, wave_height),
    }
    _obs_cache[key] = obs
    return obs


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _danger_score(wind_speed_ms: Optional[float],
                  wave_height_m: Optional[float]) -> float:
    """
    Return a 0–10 danger score combining wind and wave severity.
    0 = perfectly calm, 10 = extreme/storm conditions.
    """
    score = 0.0
    if wind_speed_ms is not None:
        # Beaufort-inspired: 0=calm, 10=storm (>24.5 m/s)
        score += min(wind_speed_ms / 24.5, 1.0) * 5.0
    if wave_height_m is not None:
        # Douglas scale: 0=glassy, 10=phenomenal (>14 m)
        score += min(wave_height_m / 14.0, 1.0) * 5.0
    return round(score, 2)


def _condition_label(wind_speed_ms: Optional[float],
                     wave_height_m: Optional[float]) -> str:
    """Return a human-readable sea condition label."""
    score = _danger_score(wind_speed_ms, wave_height_m)
    if score < 1.5:
        return 'Calm'
    if score < 3.0:
        return 'Light'
    if score < 4.5:
        return 'Moderate'
    if score < 6.0:
        return 'Rough'
    if score < 8.0:
        return 'Very Rough'
    return 'Storm'
