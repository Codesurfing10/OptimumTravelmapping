/**
 * OptimumTravelMapping — Leaflet.js map controller.
 * Handles: map initialisation, buoy layer, route visualisation, weather panels.
 */

// ── Map ────────────────────────────────────────────────────────────────────

const map = L.map('map', {
  center: CONFIG.MAP_CENTER,
  zoom: CONFIG.MAP_ZOOM,
  zoomControl: true,
});

// Esri Ocean Basemap (beautiful ocean chart style)
L.tileLayer(
  'https://services.arcgisonline.com/ArcGIS/rest/services/Ocean/World_Ocean_Base/MapServer/tile/{z}/{y}/{x}',
  {
    attribution: 'Tiles &copy; Esri — NOAA, National Geographic, DeLorme, HERE',
    maxZoom: 13,
  }
).addTo(map);

// OpenSeaMap navigation overlay (nautical marks, depth contours)
L.tileLayer('https://tiles.openseamap.org/seamark/{z}/{x}/{y}.png', {
  attribution: '&copy; <a href="https://www.openseamap.org">OpenSeaMap</a>',
  opacity: 0.7,
  maxZoom: 13,
}).addTo(map);

// ── Layer groups ───────────────────────────────────────────────────────────

const buoyLayer = L.layerGroup().addTo(map);
const routeLayer = L.layerGroup().addTo(map);
const waypointLayer = L.layerGroup().addTo(map);
const markerLayer = L.layerGroup().addTo(map);   // start/end markers

// ── State ──────────────────────────────────────────────────────────────────

const state = {
  routeStart: null,   // [lat, lon]
  routeEnd: null,     // [lat, lon]
  picking: null,      // 'start' | 'end' | null
  buoysLoaded: false,
};

// ── Buoy icons ─────────────────────────────────────────────────────────────

function buoyIcon(colour) {
  return L.divIcon({
    className: '',
    html: `<div class="buoy-marker" style="background:${colour};border-color:${colour}88"></div>`,
    iconSize: [14, 14],
    iconAnchor: [7, 7],
    popupAnchor: [0, -10],
  });
}

function dangerColour(score) {
  if (score < 2)  return '#2ecc71';
  if (score < 4)  return '#f1c40f';
  if (score < 6)  return '#e67e22';
  if (score < 8)  return '#e74c3c';
  return '#8e44ad';
}

function formatVal(v, unit = '', decimals = 1) {
  return v != null ? `${Number(v).toFixed(decimals)}${unit}` : 'N/A';
}

// ── Load buoys ─────────────────────────────────────────────────────────────

async function loadBuoys() {
  setStatus('Loading NDBC buoy observations…');
  try {
    const data = await API.buoyObservations();
    buoyLayer.clearLayers();

    let shown = 0;
    const max = CONFIG.MAX_BUOYS_ON_LOAD || Infinity;

    for (const feature of data.features) {
      if (shown >= max) break;
      const props = feature.properties;
      const [lon, lat] = feature.geometry.coordinates;
      const colour = dangerColour(props.danger_score || 0);

      const marker = L.marker([lat, lon], { icon: buoyIcon(colour) });
      marker.bindPopup(buildBuoyPopup(props));
      buoyLayer.addLayer(marker);
      shown++;
    }

    state.buoysLoaded = true;
    setStatus(`Loaded ${shown} buoy observations. Click map to set route points.`);
  } catch (e) {
    setStatus('⚠ Could not load buoy data. Check API connection.', true);
  }
}

function buildBuoyPopup(props) {
  const colour = dangerColour(props.danger_score || 0);
  return `
    <div class="buoy-popup">
      <div class="bp-header" style="border-left:4px solid ${colour}">
        <strong>Buoy ${props.id}</strong>
        <span class="bp-condition" style="color:${colour}">${props.condition || 'Unknown'}</span>
      </div>
      <table class="bp-table">
        <tr><td>🌊 Wave Height</td><td>${formatVal(props.wave_height_m, ' m')}</td></tr>
        <tr><td>💨 Wind Speed</td><td>${formatVal(props.wind_speed_ms, ' m/s')} ${windDir(props.wind_dir_deg)}</td></tr>
        <tr><td>💨 Wind Gust</td><td>${formatVal(props.wind_gust_ms, ' m/s')}</td></tr>
        <tr><td>🌡 Air Temp</td><td>${formatVal(props.air_temp_c, '°C')}</td></tr>
        <tr><td>🌡 Sea Temp</td><td>${formatVal(props.water_temp_c, '°C')}</td></tr>
        <tr><td>🕐 Updated</td><td>${props.timestamp || 'N/A'}</td></tr>
        <tr><td>⚠ Danger</td><td>${formatVal(props.danger_score, '/10')}</td></tr>
      </table>
    </div>`;
}

function windDir(deg) {
  if (deg == null) return '';
  const dirs = ['N','NE','E','SE','S','SW','W','NW'];
  return dirs[Math.round(deg / 45) % 8];
}

// ── Route planning ─────────────────────────────────────────────────────────

const pinIcon = (label, colour) => L.divIcon({
  className: '',
  html: `<div class="route-pin" style="background:${colour}"><span>${label}</span></div>`,
  iconSize: [32, 40],
  iconAnchor: [16, 40],
  popupAnchor: [0, -42],
});

map.on('click', (e) => {
  if (!state.picking) return;
  const { lat, lng } = e.latlng;

  if (state.picking === 'start') {
    state.routeStart = [lat, lng];
    updatePinOnMap('start', lat, lng);
    document.getElementById('start-coords').textContent = `${lat.toFixed(4)}, ${lng.toFixed(4)}`;
    setPickMode(null);
    setStatus('Start set. Now click "Set End Point" or enter coordinates manually.');
  } else if (state.picking === 'end') {
    state.routeEnd = [lat, lng];
    updatePinOnMap('end', lat, lng);
    document.getElementById('end-coords').textContent = `${lat.toFixed(4)}, ${lng.toFixed(4)}`;
    setPickMode(null);
    setStatus('End set. Click "Optimize Route" when ready.');
  }
});

function updatePinOnMap(type, lat, lon) {
  // Remove existing pin of this type
  markerLayer.eachLayer((layer) => {
    if (layer._pinType === type) markerLayer.removeLayer(layer);
  });
  const colour = type === 'start' ? '#2ecc71' : '#e74c3c';
  const label = type === 'start' ? 'A' : 'B';
  const m = L.marker([lat, lon], { icon: pinIcon(label, colour) });
  m._pinType = type;
  m.addTo(markerLayer);
}

function setPickMode(mode) {
  state.picking = mode;
  map.getContainer().style.cursor = mode ? 'crosshair' : '';
  document.getElementById('pick-start-btn').classList.toggle('active', mode === 'start');
  document.getElementById('pick-end-btn').classList.toggle('active', mode === 'end');
}

// ── Optimize route ─────────────────────────────────────────────────────────

async function optimizeRoute() {
  if (!state.routeStart || !state.routeEnd) {
    setStatus('⚠ Please set both start and end points first.', true);
    return;
  }

  const [sLat, sLon] = state.routeStart;
  const [eLat, eLon] = state.routeEnd;

  setStatus('Optimizing route — fetching weather data…');
  document.getElementById('optimize-btn').disabled = true;

  try {
    const result = await API.optimizeRoute(sLat, sLon, eLat, eLon);
    drawRoute(result);
    showSummary(result.summary);
    setStatus('✓ Route optimized. See summary panel.');
  } catch (e) {
    setStatus('⚠ Route optimization failed: ' + e.message, true);
  } finally {
    document.getElementById('optimize-btn').disabled = false;
  }
}

function drawRoute(geojson) {
  routeLayer.clearLayers();
  waypointLayer.clearLayers();

  for (const feature of geojson.features) {
    const props = feature.properties;

    if (feature.geometry.type === 'LineString') {
      const coords = feature.geometry.coordinates.map(([lon, lat]) => [lat, lon]);
      const colour = props.colour || (props.route_type === 'optimal' ? '#00d4ff' : '#e74c3c55');
      const weight = props.route_type === 'optimal' ? 4 : 2;
      const dash = props.route_type === 'direct' ? '8,8' : null;

      L.polyline(coords, {
        color: colour,
        weight,
        opacity: props.route_type === 'direct' ? 0.5 : 1,
        dashArray: dash,
      })
        .bindTooltip(props.route_type === 'optimal' ? '✓ Optimal Route' : 'Direct Route')
        .addTo(routeLayer);

    } else if (feature.geometry.type === 'Point') {
      const [lon, lat] = feature.geometry.coordinates;
      const danger = props.danger_score || 0;
      const colour = props.colour || dangerColour(danger);

      L.circleMarker([lat, lon], {
        radius: 6,
        fillColor: colour,
        color: '#0a192f',
        weight: 1.5,
        fillOpacity: 0.9,
      })
        .bindPopup(buildWaypointPopup(props))
        .addTo(waypointLayer);
    }
  }

  // Fit map to route
  const allCoords = geojson.features
    .filter(f => f.geometry.type === 'LineString' && f.properties.route_type === 'optimal')
    .flatMap(f => f.geometry.coordinates.map(([lon, lat]) => [lat, lon]));
  if (allCoords.length) map.fitBounds(allCoords, { padding: [40, 40] });
}

function buildWaypointPopup(props) {
  const colour = props.colour || dangerColour(props.danger_score || 0);
  return `
    <div class="buoy-popup">
      <div class="bp-header" style="border-left:4px solid ${colour}">
        <strong>Waypoint</strong>
        <span class="bp-condition" style="color:${colour}">${props.condition || 'Unknown'}</span>
      </div>
      <table class="bp-table">
        <tr><td>🌊 Wave Height</td><td>${formatVal(props.wave_height_m, ' m')}</td></tr>
        <tr><td>💨 Wind Speed</td><td>${formatVal(props.wind_speed_ms, ' m/s')}</td></tr>
        <tr><td>🌧 Precip Prob</td><td>${props.precip_pct != null ? props.precip_pct + '%' : 'N/A'}</td></tr>
        <tr><td>⚠ Danger Score</td><td>${formatVal(props.danger_score, '/10')}</td></tr>
        <tr><td>📡 Source</td><td>${props.source || 'N/A'}</td></tr>
        ${props.nearest_buoy ? `<tr><td>🔵 Nearest Buoy</td><td>${props.nearest_buoy}</td></tr>` : ''}
      </table>
    </div>`;
}

function showSummary(summary) {
  if (!summary) return;
  const panel = document.getElementById('summary-panel');
  const rec = summary.recommendation || '';
  const recClass = summary.optimal_avg_danger < 3 ? 'safe'
                 : summary.optimal_avg_danger < 6 ? 'caution' : 'danger';
  panel.innerHTML = `
    <h3>📊 Route Analysis</h3>
    <div class="summary-rec ${recClass}">${rec}</div>
    <table class="bp-table">
      <tr><td>📏 Distance</td><td>${summary.distance_km} km</td></tr>
      <tr><td>🟢 Optimal Danger</td><td>${summary.optimal_avg_danger}/10</td></tr>
      <tr><td>🔴 Direct Danger</td><td>${summary.direct_avg_danger}/10</td></tr>
      <tr><td>📈 Improvement</td><td>${summary.improvement_pct}%</td></tr>
      <tr><td>🛣 Lanes Checked</td><td>${summary.lanes_evaluated}</td></tr>
    </table>
    <div class="legend">
      <span style="color:#2ecc71">■</span> Calm
      <span style="color:#f1c40f">■</span> Moderate
      <span style="color:#e67e22">■</span> Rough
      <span style="color:#e74c3c">■</span> Very Rough
      <span style="color:#8e44ad">■</span> Storm
    </div>`;
  panel.style.display = 'block';
}

// ── Status bar ─────────────────────────────────────────────────────────────

function setStatus(msg, isError = false) {
  const el = document.getElementById('status-bar');
  el.textContent = msg;
  el.className = 'status-bar' + (isError ? ' error' : '');
}

// ── Coordinate input helpers ───────────────────────────────────────────────

function parseCoordInput(idLat, idLon) {
  const lat = parseFloat(document.getElementById(idLat).value);
  const lon = parseFloat(document.getElementById(idLon).value);
  if (isNaN(lat) || isNaN(lon)) return null;
  if (lat < -90 || lat > 90 || lon < -180 || lon > 180) return null;
  return [lat, lon];
}

function applyManualCoords(type) {
  const coord = parseCoordInput(`${type}-lat`, `${type}-lon`);
  if (!coord) { setStatus(`⚠ Invalid ${type} coordinates.`, true); return; }
  const [lat, lon] = coord;
  if (type === 'start') {
    state.routeStart = coord;
    document.getElementById('start-coords').textContent = `${lat.toFixed(4)}, ${lon.toFixed(4)}`;
    updatePinOnMap('start', lat, lon);
  } else {
    state.routeEnd = coord;
    document.getElementById('end-coords').textContent = `${lat.toFixed(4)}, ${lon.toFixed(4)}`;
    updatePinOnMap('end', lat, lon);
  }
  map.setView(coord, Math.max(map.getZoom(), 5));
  setStatus(`${type.charAt(0).toUpperCase() + type.slice(1)} point set.`);
}

function clearRoute() {
  routeLayer.clearLayers();
  waypointLayer.clearLayers();
  markerLayer.clearLayers();
  state.routeStart = null;
  state.routeEnd = null;
  document.getElementById('start-coords').textContent = 'Not set';
  document.getElementById('end-coords').textContent = 'Not set';
  document.getElementById('summary-panel').style.display = 'none';
  setStatus('Route cleared. Click map or enter coordinates to plan a new route.');
}

// ── Init ───────────────────────────────────────────────────────────────────

(async () => {
  setStatus('Connecting to NOAA data services…');
  try {
    await API.health();
    setStatus('Connected. Loading buoy network…');
    loadBuoys();
  } catch {
    setStatus(
      '⚠ Backend API unreachable. Update API_BASE_URL in docs/js/config.js and redeploy.',
      true
    );
  }
})();
