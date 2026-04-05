import xml.etree.ElementTree as ET
import math
from datetime import datetime
import sys

# Parse GPX
tree = ET.parse(r'c:\Users\dweppeler\Downloads\bad-iburg-3.gpx')
root = tree.getroot()
ns = {'gpx': 'http://www.topografix.com/GPX/1/1', 'gpxtpx': 'http://www.garmin.com/xmlschemas/TrackPointExtension/v1'}

points = []
for trkpt in root.findall('.//gpx:trkpt', ns):
    lat = float(trkpt.get('lat'))
    lon = float(trkpt.get('lon'))
    ele = float(trkpt.find('gpx:ele', ns).text)
    time_str = trkpt.find('gpx:time', ns).text
    points.append({'lat': lat, 'lon': lon, 'ele': ele, 'time': time_str})

def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * 2 * math.asin(math.sqrt(a))

# GPXray gradient multiplier (from API)
def get_gradient_multiplier(grade):
    if grade >= 0:
        # Uphill
        if grade <= 5:
            mult = 1.0 + (grade / 5) * 0.3
        elif grade <= 10:
            mult = 1.3 + ((grade - 5) / 5) * 0.4
        elif grade <= 15:
            mult = 1.7 + ((grade - 10) / 5) * 0.3
        else:
            mult = 2.0 + ((grade - 15) / 10) * 0.2
        mult = min(mult, 2.2)
    else:
        # Downhill
        abs_grade = abs(grade)
        if abs_grade <= 5:
            mult = 1.0 - (abs_grade / 5) * 0.1
        elif abs_grade <= 10:
            mult = 0.9 - ((abs_grade - 5) / 5) * 0.05
        else:
            mult = 0.85
        mult = max(mult, 0.85)
    return mult

# Intermediate runner - your flat RACE pace would be ~6:00-6:30
# But this was TRAINING, so add ~15% slower than race effort
flat_race_pace = 6.5  # Intermediate preset
training_factor = 1.15  # Training runs ~15% slower than race
flat_pace = flat_race_pace * training_factor  # ~7.5 min/km effective

# Calculate actual and predicted splits per km
km_data = []
current_km = 1
km_start_idx = 0
km_distance = 0
km_predicted_time = 0

for i in range(1, len(points)):
    dist = haversine(points[i-1]['lat'], points[i-1]['lon'], points[i]['lat'], points[i]['lon'])
    ele_diff = points[i]['ele'] - points[i-1]['ele']
    grade = (ele_diff / (dist * 1000)) * 100 if dist > 0 else 0
    
    multiplier = get_gradient_multiplier(grade)
    predicted_time = dist * flat_pace * multiplier
    
    km_distance += dist
    km_predicted_time += predicted_time
    
    if km_distance >= 1.0:
        # Get actual time
        t0 = datetime.fromisoformat(points[km_start_idx]['time'].replace('Z', '+00:00'))
        t1 = datetime.fromisoformat(points[i]['time'].replace('Z', '+00:00'))
        actual_sec = (t1 - t0).total_seconds()
        actual_min = actual_sec / 60
        
        ele_start = points[km_start_idx]['ele']
        ele_end = points[i]['ele']
        ele_delta = ele_end - ele_start
        
        km_data.append({
            'km': current_km,
            'actual': actual_min,
            'predicted': km_predicted_time,
            'ele': ele_delta,
            'diff': actual_min - km_predicted_time
        })
        
        current_km += 1
        km_start_idx = i
        km_distance = 0
        km_predicted_time = 0

# Summary
total_actual = sum(d['actual'] for d in km_data)
total_predicted = sum(d['predicted'] for d in km_data)

print('=== GPXray PREDICTION vs ACTUAL ===')
print(f'Intermediate runner, training effort')
print(f'Estimated flat pace: {flat_pace:.1f} min/km (race: {flat_race_pace}/km + 15% training)')
print()
print('KM    Actual   Predict  Diff     Elev')
print('-' * 50)
for d in km_data:
    act_m = int(d['actual'])
    act_s = int((d['actual'] - act_m) * 60)
    pred_m = int(d['predicted'])
    pred_s = int((d['predicted'] - pred_m) * 60)
    diff = d['diff']
    diff_sign = '+' if diff > 0 else ''
    ele = ('+' if d['ele'] >= 0 else '') + str(int(d['ele']))
    print(f"{d['km']:2}    {act_m}:{act_s:02d}     {pred_m}:{pred_s:02d}    {diff_sign}{diff:.1f}min  {ele}m")

print('-' * 50)
act_h = int(total_actual // 60)
act_m = int(total_actual % 60)
pred_h = int(total_predicted // 60)
pred_m = int(total_predicted % 60)
print(f'Total: {act_h}:{act_m:02d} actual vs {pred_h}:{pred_m:02d} predicted')
print(f'Diff: {total_actual - total_predicted:.1f} min ({((total_actual - total_predicted) / total_predicted * 100):.1f}%)')

# Analyze prediction accuracy
uphill_kms = [d for d in km_data if d['ele'] > 20]
downhill_kms = [d for d in km_data if d['ele'] < -20]
flat_kms = [d for d in km_data if -20 <= d['ele'] <= 20]

print()
print('=== ACCURACY BY TERRAIN ===')
if uphill_kms:
    avg_diff = sum(d['diff'] for d in uphill_kms) / len(uphill_kms)
    print(f'Uphill ({len(uphill_kms)} kms): Avg diff {avg_diff:+.1f} min/km')
if downhill_kms:
    avg_diff = sum(d['diff'] for d in downhill_kms) / len(downhill_kms)
    print(f'Downhill ({len(downhill_kms)} kms): Avg diff {avg_diff:+.1f} min/km')
if flat_kms:
    avg_diff = sum(d['diff'] for d in flat_kms) / len(flat_kms)
    print(f'Flat ({len(flat_kms)} kms): Avg diff {avg_diff:+.1f} min/km')
