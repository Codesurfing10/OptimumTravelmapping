# 🌊 OptimumTravelMapping

**NOAA-powered ocean travel route planner** — uses real-time NDBC buoy observations and NOAA gridpoint weather forecasts to identify the safest path between two ocean coordinates, accounting for wave height, wind speed, precipitation, and swell.

| Layer | Technology | Hosted |
|-------|-----------|--------|
| **Frontend UI** | HTML · CSS · Leaflet.js | GitHub Pages |
| **Backend API** | Python · Flask · NOAA APIs | Render |

🔗 **Live UI:** `https://codesurfing10.github.io/OptimumTravelmapping`  
🔗 **API:** `https://optimum-travel-mapping-api.onrender.com`

---

## Features

- 🗺 **Esri Ocean + OpenSeaMap** basemap with nautical marks and depth contours
- 📡 **NOAA NDBC** buoy observations (wave height, wind speed, sea temperature, pressure)
- ⚡ **Route Optimizer** — evaluates 5 lateral lanes × 12 waypoints, scores each by combined wave/wind/rain danger, returns the safest path as GeoJSON
- 🌧 **NOAA Weather API** gridpoint forecasts for US coastal waters
- 🎨 Colour-coded danger markers: Calm → Moderate → Rough → Very Rough → Storm
- 📊 Route analysis summary with distance, danger comparison, and recommendation

---

## Architecture

```
┌────────────────────────────┐        ┌──────────────────────────────┐
│   GitHub Pages (Frontend)  │  HTTPS │   Render (Python Flask API)  │
│   docs/index.html          │◄──────►│   app.py                     │
│   docs/js/{config,api,map} │        │   api/noaa_ndbc.py           │
│   docs/css/styles.css      │        │   api/noaa_weather.py        │
└────────────────────────────┘        │   core/grid_mapping.py       │
                                       │   core/route_optimizer.py    │
                                       └──────────────────────────────┘
                                                     │
                                       ┌─────────────┴───────────────┐
                                       │    NOAA Public APIs         │
                                       │  ndbc.noaa.gov (buoys)      │
                                       │  api.weather.gov (forecast) │
                                       └─────────────────────────────┘
```

---

## Deployment

### 1 — Backend on Render

1. Sign in at [render.com](https://render.com) → **New → Web Service**
2. Connect this GitHub repository (`Codesurfing10/OptimumTravelmapping`)
3. Render will auto-detect `render.yaml` and configure the service
4. Set the environment variable if desired:
   ```
   NOAA_USER_AGENT = OptimumTravelMapping/1.0 (your-email@example.com)
   ```
5. Deploy — your API will be live at `https://optimum-travel-mapping-api.onrender.com`

> **Note:** The free Render tier spins down after 15 min of inactivity; first request after sleep may take ~30 s.

### 2 — Frontend on GitHub Pages

1. Go to **Settings → Pages** in this repository
2. Set **Source** to `Deploy from a branch`
3. Set **Branch** to `main` and **Folder** to `/docs`
4. Save — the UI will be live at `https://codesurfing10.github.io/OptimumTravelmapping`

### 3 — Connect UI to API

Edit `docs/js/config.js` and set `API_BASE_URL` to your Render service URL:
```js
const CONFIG = {
  API_BASE_URL: 'https://optimum-travel-mapping-api.onrender.com',
  ...
};
```
Commit and push — GitHub Pages will auto-redeploy.

---

## Local Development

```bash
# Clone the repo
git clone https://github.com/Codesurfing10/OptimumTravelmapping.git
cd OptimumTravelmapping

# Create virtual environment
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# (Optional) copy and edit env vars
cp .env.example .env

# Run the Flask API
python app.py
# → http://localhost:5000
```

To view the UI locally, open `docs/index.html` in your browser and temporarily change `API_BASE_URL` in `docs/js/config.js` to `http://localhost:5000`.

---

## API Reference

All endpoints are prefixed with `/api`.

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check |
| `GET` | `/buoys` | List active NDBC stations |
| `GET` | `/buoys/observations` | Latest bulk buoy observations (GeoJSON) |
| `GET` | `/buoys/<id>` | Single buoy realtime data |
| `GET` | `/weather?lat=&lon=` | NOAA gridpoint forecast |
| `GET` | `/weather/grid?lat=&lon=` | Raw grid conditions for scoring |
| `POST` | `/route/optimize` | Optimize route between two coordinates |

**Route optimization request body:**
```json
{
  "start": { "lat": 25.77, "lon": -80.19 },
  "end":   { "lat": 40.71, "lon": -74.01 },
  "waypoints": 12,
  "lanes": 5
}
```

---

## Data Sources

| Source | Data | Notes |
|--------|------|-------|
| [NOAA NDBC](https://www.ndbc.noaa.gov) | Buoy observations (waves, wind, temp) | Free, no auth required |
| [NOAA Weather API](https://api.weather.gov) | Gridpoint forecasts, marine conditions | Free, User-Agent required |
| [Esri Ocean Basemap](https://www.esri.com/en-us/arcgis/products/arcgis-living-atlas/overview) | Ocean chart tile layer | Free for development |
| [OpenSeaMap](https://www.openseamap.org) | Nautical marks overlay | Free, CC BY-SA |

---

## License

MIT — see [LICENSE](LICENSE)
