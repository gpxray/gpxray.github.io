# GPXray Backend API

Azure Functions backend to protect calculation algorithms.

## Protected Logic

The following algorithms are protected in the backend:
- `RUNNER_LEVELS` - Pace presets by experience level
- `get_fatigue_multiplier()` - Ultra-distance fatigue curves
- `SURFACE_TYPES` - Terrain surface multipliers
- `calculate_race_plan()` - Main calculation engine

## Local Development

### Option 1: Simple Local Server (no Azure tools needed)

```bash
cd api
python local_server.py
```

### Option 2: Azure Functions Core Tools

```bash
# Install Azure Functions Core Tools first
# https://learn.microsoft.com/en-us/azure/azure-functions/functions-run-local

cd api
pip install -r requirements.txt
func start
```

API will be available at: `http://localhost:7071/api/calculate`

## Frontend Configuration

In `app.js`, set the API configuration:

```javascript
const API_CONFIG = {
    calculateEndpoint: 'http://localhost:7071/api/calculate',  // Local dev
    // calculateEndpoint: 'https://gpxray-api.azurewebsites.net/api/calculate',  // Production
    useBackend: true,   // Enable API calls
    timeout: 10000
};
```

## Deploy to Azure

```bash
# Login to Azure
az login

# Create Function App (one-time)
az functionapp create \
  --resource-group gpxray-rg \
  --consumption-plan-location westeurope \
  --runtime python \
  --runtime-version 3.9 \
  --functions-version 4 \
  --name gpxray-api \
  --storage-account gpxraystorage

# Deploy
cd api
func azure functionapp publish gpxray-api
```

## API Usage

### POST /api/calculate

Request:
```json
{
  "segments": [
    {"distance": 1.0, "terrainType": "uphill", "surfaceType": "trail", "startDistance": 0, "endDistance": 1}
  ],
  "runnerLevel": "intermediate",
  "aidStations": [
    {"km": 18.4, "name": "VP1", "stopMin": 3}
  ],
  "applySurface": true,
  "startTime": "06:20",
  "totalDistance": 77
}
```

Response:
```json
{
  "totalTimeMinutes": 744.5,
  "totalTimeFormatted": "12:24:30",
  "finishClockTime": "18:44",
  "fatigueMultiplier": 1.25,
  "paces": {
    "flat": 6.5,
    "uphill": 9.1,
    "downhill": 5.525
  },
  "checkpoints": [
    {"name": "VP1", "km": 18.4, "timeMinutes": 172.5}
  ],
  "stopTimeMinutes": 21
}
```

## Frontend Integration

Replace direct calculation calls with API calls:

```javascript
async function calculateRacePlanFromAPI() {
    const response = await fetch('https://gpxray-api.azurewebsites.net/api/calculate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            segments: segments,
            runnerLevel: document.getElementById('runnerLevel').value,
            aidStations: aidStations,
            applySurface: document.getElementById('surfaceEnabled')?.checked,
            startTime: document.getElementById('raceStartTime').value,
            totalDistance: gpxData.totalDistance
        })
    });
    
    const result = await response.json();
    // Use result.totalTimeFormatted, result.checkpoints, etc.
}
```
