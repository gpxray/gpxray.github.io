import xml.etree.ElementTree as ET
from datetime import datetime
import math

def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

def extract_splits(path):
    tree = ET.parse(path)
    root = tree.getroot()
    pts = root.findall('.//{http://www.topografix.com/GPX/1/1}trkpt')
    
    splits = []
    cum_dist = 0
    last_km = 0
    last_km_idx = 0
    start_time = None
    
    for i in range(len(pts)):
        t_el = pts[i].find('.//{http://www.topografix.com/GPX/1/1}time')
        if t_el is None: continue
        t = datetime.fromisoformat(t_el.text.replace('Z', '+00:00'))
        if start_time is None: start_time = t
        
        if i > 0:
            lat1, lon1 = float(pts[i-1].get('lat')), float(pts[i-1].get('lon'))
            lat2, lon2 = float(pts[i].get('lat')), float(pts[i].get('lon'))
            cum_dist += haversine(lat1, lon1, lat2, lon2)
        
        km = int(cum_dist)
        if km > last_km and km <= 35:
            elapsed = (t - start_time).total_seconds() / 60
            split_time = elapsed - (splits[-1]['cum'] if splits else 0)
            
            ele_start = pts[last_km_idx].find('.//{http://www.topografix.com/GPX/1/1}ele')
            ele_end = pts[i].find('.//{http://www.topografix.com/GPX/1/1}ele')
            ele_change = 0
            if ele_start is not None and ele_end is not None:
                ele_change = float(ele_end.text) - float(ele_start.text)
            grade = ele_change / 10
            
            splits.append({'km': km, 'split': round(split_time, 1), 'cum': round(elapsed, 1), 'grade': round(grade, 1)})
            last_km = km
            last_km_idx = i
    
    return splits

# Collect all data
all_data = []
files = [
    ('c:/Users/dweppeler/Downloads/bad iburg 1.gpx', 'BI1'),
    ('c:/Users/dweppeler/Downloads/bad iburg 2.gpx', 'BI2'),
    ('c:/Users/dweppeler/Downloads/klippenlauf.gpx', 'KLP')
]

for path, name in files:
    splits = extract_splits(path)
    for s in splits:
        all_data.append((name, s['km'], s['grade'], s['split']))

# Grade-based analysis
print("\n=== GRADE vs PACE ANALYSIS (4 workouts combined) ===\n")
print("Grade Bucket      | Count | Avg Pace | Multiplier")
print("------------------|-------|----------|------------")

buckets = {}
for name, km, grade, split in all_data:
    if grade < -10: bucket = '<-10%'
    elif grade < -5: bucket = '-10 to -5%'
    elif grade < -2: bucket = '-5 to -2%'
    elif grade < 2: bucket = '-2 to 2%'
    elif grade < 5: bucket = '2 to 5%'
    elif grade < 8: bucket = '5 to 8%'
    elif grade < 12: bucket = '8 to 12%'
    else: bucket = '>12%'
    
    if bucket not in buckets:
        buckets[bucket] = []
    buckets[bucket].append(split)

order = ['<-10%', '-10 to -5%', '-5 to -2%', '-2 to 2%', '2 to 5%', '5 to 8%', '8 to 12%', '>12%']
for bucket in order:
    if bucket in buckets:
        data = buckets[bucket]
        avg = sum(data) / len(data)
        mult = avg / 6.0
        print(f"{bucket:17} | {len(data):5} | {avg:7.1f}  | {mult:.2f}x")

# Steep uphills detail
print("\n=== STEEP UPHILLS (>8% grade) ===\n")
print("Source | KM | Grade  | Pace   | x Flat")
print("-------|----|---------|---------|---------")
for name, km, grade, split in all_data:
    if grade > 8:
        mult = split / 6.0
        print(f"{name:6} | {km:2} |  +{grade:4.1f}% | {split:5.1f}m | {mult:.2f}x")

# Very steep uphills
print("\n=== VERY STEEP UPHILLS (>12% grade) ===\n")
for name, km, grade, split in all_data:
    if grade > 12:
        mult = split / 6.0
        print(f"{name} KM{km}: +{grade:.1f}% -> {split:.1f}min/km ({mult:.2f}x flat)")

# Steep downhills detail
print("\n=== STEEP DOWNHILLS (<-8% grade) ===\n")
print("Source | KM | Grade   | Pace   | x Flat")
print("-------|----|---------|---------|---------")
for name, km, grade, split in all_data:
    if grade < -8:
        mult = split / 6.0
        print(f"{name:6} | {km:2} |  {grade:5.1f}% | {split:5.1f}m | {mult:.2f}x")

# Proposed formula
print("\n=== PROPOSED GPXRAY FORMULA ===\n")
print("Current GPXray:")
print("  Uphill: 1.5x flat pace (fixed)")
print("  Downhill: 0.83x flat pace (fixed)")
print()
print("Proposed (grade-scaled):")
print("  grade <= -10%: 1.1x (technical descent)")
print("  grade -10 to -5%: 1.0x")
print("  grade -5 to -2%: 0.95x")
print("  grade -2 to +2%: 1.0x (flat)")
print("  grade +2 to +5%: 1.2x")
print("  grade +5 to +8%: 1.6x")
print("  grade +8 to +12%: 1.8x")
print("  grade > +12%: 2.2x")
