import os

# Load .env if present (local development)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


class Config:
    # NOAA Weather API (api.weather.gov) — requires a descriptive User-Agent
    NOAA_USER_AGENT = os.getenv(
        'NOAA_USER_AGENT',
        'OptimumTravelMapping/1.0 (github.com/Codesurfing10)'
    )
    NOAA_WEATHER_API = 'https://api.weather.gov'

    # NOAA National Data Buoy Center (NDBC) — no auth required
    NOAA_NDBC_BASE = 'https://www.ndbc.noaa.gov'

    # In-memory cache TTL in seconds (30 minutes for buoy data, 1 hour for forecasts)
    BUOY_CACHE_TTL = 1800
    FORECAST_CACHE_TTL = 3600

    # CORS — allow GitHub Pages origin plus localhost for development
    CORS_ORIGINS = os.getenv(
        'CORS_ORIGIN',
        'https://codesurfing10.github.io,http://localhost:3000,http://127.0.0.1:5000'
    ).split(',')

    # Route optimizer settings
    ROUTE_WAYPOINTS = 12        # Number of intermediate waypoints per route segment
    ROUTE_GRID_OFFSETS = 5      # Lateral grid candidates to evaluate per segment
    MAX_SAFE_WAVE_HEIGHT = 2.5  # metres — above this is flagged as rough
    MAX_SAFE_WIND_SPEED = 10.0  # m/s (~20 kt) — above this adds risk
