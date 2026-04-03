/**
 * API client — wraps all calls to the Render backend.
 */
const API = (() => {
  const base = () => CONFIG.API_BASE_URL;

  async function _fetch(path, options = {}) {
    const url = `${base()}${path}`;
    try {
      const res = await fetch(url, {
        headers: { 'Content-Type': 'application/json' },
        ...options,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ error: res.statusText }));
        throw new Error(err.error || `HTTP ${res.status}`);
      }
      return res.json();
    } catch (e) {
      console.error(`API error [${path}]:`, e);
      throw e;
    }
  }

  return {
    health: () => _fetch('/api/health'),

    /** Fetch latest NDBC buoy observations as GeoJSON FeatureCollection */
    buoyObservations: (lat, lon, radiusKm) => {
      let qs = '';
      if (lat != null && lon != null && radiusKm) {
        qs = `?lat=${lat}&lon=${lon}&radius_km=${radiusKm}`;
      }
      return _fetch(`/api/buoys/observations${qs}`);
    },

    /** Fetch individual buoy detail */
    buoyDetail: (stationId) => _fetch(`/api/buoys/${stationId}`),

    /** Fetch NOAA gridpoint forecast for lat/lon */
    forecast: (lat, lon, hourly = false) =>
      _fetch(`/api/weather?lat=${lat}&lon=${lon}${hourly ? '&hourly=1' : ''}`),

    /** Optimize a route between two coordinates */
    optimizeRoute: (startLat, startLon, endLat, endLon, waypoints = 12, lanes = 5) =>
      _fetch('/api/route/optimize', {
        method: 'POST',
        body: JSON.stringify({
          start: { lat: startLat, lon: startLon },
          end: { lat: endLat, lon: endLon },
          waypoints,
          lanes,
        }),
      }),
  };
})();
