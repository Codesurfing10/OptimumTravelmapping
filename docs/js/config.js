/**
 * API configuration for OptimumTravelMapping.
 *
 * Set API_BASE_URL to your deployed Render backend URL.
 * During local development set it to http://localhost:5000
 */
const CONFIG = {
  // Replace with your Render service URL after deployment
  API_BASE_URL: 'https://optimum-travel-mapping-api.onrender.com',

  MAP_CENTER: [30.0, -65.0],  // Mid-Atlantic / Caribbean default view
  MAP_ZOOM: 4,

  // Max NDBC buoy markers shown on initial load (improves performance on slow connections).
  // Set to 0 to show all available buoys (may be 1000+).
  MAX_BUOYS_ON_LOAD: 200,

  // Buoy radius filter (km) — set to 0 for all buoys
  BUOY_RADIUS_KM: 0,
};
