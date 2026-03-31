"""
Azure Function - GPXray Calculate API (v2 Programming Model)
For Azure Functions Flex Consumption Plan
"""
import azure.functions as func
import json
import logging

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

# Runner level presets (protected backend logic)
RUNNER_LEVELS = {
    'beginner': {
        'name': 'Beginner',
        'flatPace': 8.0,
        'uphillRatio': 1.5,
        'downhillRatio': 0.9,
        'dft': 6000
    },
    'intermediate': {
        'name': 'Intermediate',
        'flatPace': 6.5,
        'uphillRatio': 1.4,
        'downhillRatio': 0.85,
        'dft': 9000
    },
    'advanced': {
        'name': 'Advanced',
        'flatPace': 5.5,
        'uphillRatio': 1.3,
        'downhillRatio': 0.82,
        'dft': 12000
    },
    'elite': {
        'name': 'Elite',
        'flatPace': 4.5,
        'uphillRatio': 1.25,
        'downhillRatio': 0.8,
        'dft': 15000
    }
}

# Surface type multipliers
SURFACE_TYPES = {
    'road': {'flat': 1.0, 'uphill': 1.0, 'downhill': 1.0},
    'trail': {'flat': 1.05, 'uphill': 1.08, 'downhill': 1.10},
    'technical': {'flat': 1.12, 'uphill': 1.15, 'downhill': 1.20},
    'rocky': {'flat': 1.15, 'uphill': 1.18, 'downhill': 1.25},
    'sand': {'flat': 1.25, 'uphill': 1.30, 'downhill': 1.15}
}


def get_fatigue_multiplier(distance_km: float) -> float:
    """Ultra-distance fatigue multiplier - core protected algorithm"""
    if distance_km <= 21:
        return 1.0
    elif distance_km <= 42:
        return 1.05
    elif distance_km <= 50:
        return 1.12
    elif distance_km <= 65:
        return 1.18
    elif distance_km <= 80:
        return 1.25
    elif distance_km <= 100:
        return 1.32
    elif distance_km <= 130:
        return 1.40
    else:
        return 1.50


def calculate_segment_time(segment: dict, paces: dict, apply_surface: bool) -> dict:
    """Calculate time for a single segment - returns breakdown by terrain"""
    terrain = segment.get('terrainType', 'flat')
    distance = segment.get('distance', 0)
    surface = segment.get('surfaceType', 'trail')
    
    if terrain == 'uphill':
        pace = paces['uphill']
    elif terrain == 'downhill':
        pace = paces['downhill']
    else:
        pace = paces['flat']
    
    if apply_surface and surface in SURFACE_TYPES:
        pace *= SURFACE_TYPES[surface].get(terrain, 1.0)
    
    time = distance * pace
    
    return {
        'terrain': terrain,
        'distance': distance,
        'time': time
    }


def calculate_race_plan(data: dict) -> dict:
    """Main calculation function - protected business logic"""
    segments = data.get('segments', [])
    runner_level = data.get('runnerLevel', 'intermediate')
    aid_stations = data.get('aidStations', [])
    apply_surface = data.get('applySurface', False)
    start_time = data.get('startTime', '09:00')
    total_distance = data.get('totalDistance', 0)
    mode = data.get('mode', 'preset')
    manual_paces = data.get('manualPaces', None)
    
    preset = RUNNER_LEVELS.get(runner_level, RUNNER_LEVELS['intermediate'])
    
    if mode == 'manual' and manual_paces:
        flat_pace = manual_paces.get('flat', preset['flatPace'])
        uphill_pace = manual_paces.get('uphill', flat_pace * preset['uphillRatio'])
        downhill_pace = manual_paces.get('downhill', flat_pace * preset['downhillRatio'])
    else:
        flat_pace = preset['flatPace']
        uphill_pace = flat_pace * preset['uphillRatio']
        downhill_pace = flat_pace * preset['downhillRatio']
    
    paces = {
        'flat': flat_pace,
        'uphill': uphill_pace,
        'downhill': downhill_pace
    }
    
    fatigue = get_fatigue_multiplier(total_distance)
    
    flat_distance = 0
    uphill_distance = 0
    downhill_distance = 0
    flat_time = 0
    uphill_time = 0
    downhill_time = 0
    
    for segment in segments:
        result = calculate_segment_time(segment, paces, apply_surface)
        terrain = result['terrain']
        distance = result['distance']
        time = result['time']
        
        if terrain == 'flat':
            flat_distance += distance
            flat_time += time
        elif terrain == 'uphill':
            uphill_distance += distance
            uphill_time += time
        elif terrain == 'downhill':
            downhill_distance += distance
            downhill_time += time
    
    running_time = flat_time + uphill_time + downhill_time
    adjusted_running_time = running_time * fatigue
    
    total_stop_time = sum(s.get('stopMin', 0) for s in aid_stations)
    total_time = adjusted_running_time + total_stop_time
    
    checkpoints = []
    for station in sorted(aid_stations, key=lambda s: s.get('km', 0)):
        station_km = station.get('km', 0)
        time_to_station = 0
        
        for segment in segments:
            seg_start = segment.get('startDistance', 0)
            seg_end = segment.get('endDistance', 0)
            
            if seg_end <= station_km:
                result = calculate_segment_time(segment, paces, apply_surface)
                time_to_station += result['time']
            elif seg_start < station_km:
                result = calculate_segment_time(segment, paces, apply_surface)
                partial_ratio = (station_km - seg_start) / segment.get('distance', 1)
                time_to_station += result['time'] * partial_ratio
                break
        
        time_to_station *= fatigue
        
        for prev_station in aid_stations:
            if prev_station.get('km', 0) < station_km:
                time_to_station += prev_station.get('stopMin', 0)
        
        checkpoints.append({
            'name': station.get('name', 'VP'),
            'km': station_km,
            'timeMinutes': time_to_station,
            'stopMin': station.get('stopMin', 0)
        })
    
    try:
        start_parts = start_time.split(':')
        start_minutes = int(start_parts[0]) * 60 + int(start_parts[1])
    except:
        start_minutes = 9 * 60
    
    finish_minutes = start_minutes + total_time
    finish_hours = int(finish_minutes // 60) % 24
    finish_mins = int(finish_minutes % 60)
    
    total_hours = int(total_time // 60)
    total_mins = int(total_time % 60)
    total_secs = int((total_time % 1) * 60)
    
    return {
        'totalTimeMinutes': total_time,
        'totalTimeFormatted': f"{total_hours}:{total_mins:02d}:{total_secs:02d}",
        'finishClockTime': f"{finish_hours:02d}:{finish_mins:02d}",
        'fatigueMultiplier': fatigue,
        'paces': {
            'flat': flat_pace,
            'uphill': uphill_pace,
            'downhill': downhill_pace
        },
        'terrain': {
            'flatDistance': flat_distance,
            'uphillDistance': uphill_distance,
            'downhillDistance': downhill_distance,
            'flatTime': flat_time * fatigue,
            'uphillTime': uphill_time * fatigue,
            'downhillTime': downhill_time * fatigue
        },
        'checkpoints': checkpoints,
        'stopTimeMinutes': total_stop_time,
        'runnerLevel': runner_level,
        'preset': preset
    }


@app.route(route="calculate", methods=["POST", "OPTIONS"])
def calculate(req: func.HttpRequest) -> func.HttpResponse:
    """HTTP trigger for race plan calculation"""
    logging.info('Calculate API called')
    
    # CORS headers
    headers = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'POST, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type',
        'Content-Type': 'application/json'
    }
    
    # Handle preflight
    if req.method == 'OPTIONS':
        return func.HttpResponse('', status_code=200, headers=headers)
    
    try:
        data = req.get_json()
        result = calculate_race_plan(data)
        
        return func.HttpResponse(
            json.dumps(result),
            status_code=200,
            headers=headers
        )
    except Exception as e:
        logging.error(f'Calculation error: {str(e)}')
        return func.HttpResponse(
            json.dumps({'error': str(e)}),
            status_code=500,
            headers=headers
        )
