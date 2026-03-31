#!/usr/bin/env python3
"""
Surface Analyzer Tool for GPXray
================================
Pre-computes surface profile for GPX files using OpenStreetMap Overpass API.
Output format is compatible with races-config.js surfaceProfile field.

Usage:
    python surface-analyzer.py path/to/race.gpx
    python surface-analyzer.py path/to/race.gpx --output json
"""

import sys
import math
import time
import json
import argparse
import xml.etree.ElementTree as ET
import requests

# OSM surface tag to category mapping (same as app.js)
OSM_SURFACE_MAP = {
    # Road surfaces
    'asphalt': 'road', 'concrete': 'road', 'paved': 'road', 'concrete:plates': 'road',
    'concrete:lanes': 'road', 'paving_stones': 'road', 'sett': 'road', 'cobblestone': 'road',
    # Trail surfaces
    'compacted': 'trail', 'fine_gravel': 'trail', 'gravel': 'trail', 'dirt': 'trail',
    'earth': 'trail', 'ground': 'trail', 'grass': 'trail', 'unpaved': 'trail',
    'sand': 'trail', 'woodchips': 'trail', 'mud': 'trail',
    # Technical surfaces
    'rock': 'technical', 'rocks': 'technical', 'pebblestone': 'technical', 
    'stepping_stones': 'technical', 'stone': 'technical', 'boulders': 'technical'
}

# OSM highway type fallback mapping
OSM_HIGHWAY_MAP = {
    'motorway': 'road', 'trunk': 'road', 'primary': 'road', 'secondary': 'road',
    'tertiary': 'road', 'residential': 'road', 'service': 'road', 'unclassified': 'road',
    'path': 'trail', 'footway': 'trail', 'cycleway': 'trail', 'bridleway': 'trail',
    'track': 'trail', 'steps': 'technical'
}

OVERPASS_ENDPOINTS = [
    'https://overpass-api.de/api/interpreter',
    'https://overpass.kumi.systems/api/interpreter',
    'https://z.overpass-api.de/api/interpreter'
]


def haversine_distance(lat1, lon1, lat2, lon2):
    """Calculate distance between two points in km."""
    R = 6371  # Earth's radius in km
    
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)
    
    a = math.sin(delta_lat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    
    return R * c


def parse_gpx(gpx_path):
    """Parse GPX file and return list of points with distances."""
    tree = ET.parse(gpx_path)
    root = tree.getroot()
    
    # Handle namespace
    ns = {'gpx': 'http://www.topografix.com/GPX/1/1'}
    
    points = []
    total_distance = 0
    
    # Try both trkpt and rtept
    track_points = root.findall('.//gpx:trkpt', ns)
    if not track_points:
        track_points = root.findall('.//gpx:rtept', ns)
    if not track_points:
        # Try without namespace
        track_points = root.findall('.//trkpt')
        if not track_points:
            track_points = root.findall('.//rtept')
    
    prev_point = None
    for pt in track_points:
        lat = float(pt.get('lat'))
        lon = float(pt.get('lon'))
        
        if prev_point:
            total_distance += haversine_distance(
                prev_point['lat'], prev_point['lon'], lat, lon
            )
        
        points.append({
            'lat': lat,
            'lon': lon,
            'distance': total_distance
        })
        prev_point = points[-1]
    
    return points, total_distance


def sample_points(points, interval_km=0.2):
    """Sample points along route at regular intervals."""
    samples = []
    last_sample_dist = -interval_km
    
    for point in points:
        if point['distance'] - last_sample_dist >= interval_km:
            samples.append(point)
            last_sample_dist = point['distance']
    
    return samples


def calculate_bbox(points, buffer=0.001):
    """Calculate bounding box with buffer."""
    lats = [p['lat'] for p in points]
    lons = [p['lon'] for p in points]
    
    return {
        'south': min(lats) - buffer,
        'north': max(lats) + buffer,
        'west': min(lons) - buffer,
        'east': max(lons) + buffer
    }


def build_overpass_query(sample_points):
    """Build Overpass API query using around filter."""
    # Limit to ~30 points for query manageability
    step = max(1, len(sample_points) // 30)
    query_points = sample_points[::step]
    
    coord_string = ','.join(f"{p['lat']},{p['lon']}" for p in query_points)
    
    return f'''[out:json][timeout:120];
(
  way["highway"](around:50,{coord_string});
);
out body geom;'''


def query_overpass(query):
    """Query Overpass API with fallback endpoints."""
    for endpoint in OVERPASS_ENDPOINTS:
        try:
            print(f'Trying {endpoint}...')
            response = requests.post(
                endpoint,
                data={'data': query},
                headers={'Content-Type': 'application/x-www-form-urlencoded'},
                timeout=120
            )
            
            if response.ok:
                data = response.json()
                print(f'Success! Got {len(data.get("elements", []))} elements')
                return data
                
        except Exception as e:
            print(f'Failed: {e}')
            time.sleep(1)
    
    raise Exception('All Overpass endpoints failed')


def process_osm_ways(data):
    """Process OSM ways from Overpass response."""
    ways = []
    
    for element in data.get('elements', []):
        if element.get('type') != 'way' or 'geometry' not in element:
            continue
        
        tags = element.get('tags', {})
        surface = tags.get('surface')
        highway = tags.get('highway')
        
        # Determine surface category
        surface_type = 'unknown'
        if surface and surface in OSM_SURFACE_MAP:
            surface_type = OSM_SURFACE_MAP[surface]
        elif highway and highway in OSM_HIGHWAY_MAP:
            surface_type = OSM_HIGHWAY_MAP[highway]
        
        ways.append({
            'id': element['id'],
            'surfaceType': surface_type,
            'surfaceTag': surface,
            'highway': highway,
            'geometry': [(g['lat'], g['lon']) for g in element['geometry']]
        })
    
    return ways


def point_to_line_distance(px, py, x1, y1, x2, y2):
    """Calculate perpendicular distance from point to line segment (approx km)."""
    A = px - x1
    B = py - y1
    C = x2 - x1
    D = y2 - y1
    
    dot = A * C + B * D
    len_sq = C * C + D * D
    
    if len_sq == 0:
        return haversine_distance(px, py, x1, y1)
    
    param = dot / len_sq
    
    if param < 0:
        xx, yy = x1, y1
    elif param > 1:
        xx, yy = x2, y2
    else:
        xx = x1 + param * C
        yy = y1 + param * D
    
    return haversine_distance(px, py, xx, yy)


def match_points_to_ways(sample_points, ways):
    """Match sample points to nearest OSM ways."""
    results = []
    
    for point in sample_points:
        nearest_way = None
        min_distance = float('inf')
        
        for way in ways:
            for i in range(len(way['geometry']) - 1):
                dist = point_to_line_distance(
                    point['lat'], point['lon'],
                    way['geometry'][i][0], way['geometry'][i][1],
                    way['geometry'][i+1][0], way['geometry'][i+1][1]
                )
                
                if dist < min_distance:
                    min_distance = dist
                    nearest_way = way
        
        # Only accept matches within ~50 meters
        if nearest_way and min_distance < 0.05:
            results.append({
                'distance': point['distance'],
                'surfaceType': nearest_way['surfaceType'],
                'surfaceTag': nearest_way.get('surfaceTag'),
                'matchDistance': min_distance
            })
        else:
            results.append({
                'distance': point['distance'],
                'surfaceType': 'unknown',
                'surfaceTag': None,
                'matchDistance': min_distance if nearest_way else float('inf')
            })
    
    return results


def build_surface_profile(surface_results, total_distance):
    """Build consolidated surface profile from sample results."""
    if not surface_results:
        return []
    
    # Sort by distance
    sorted_results = sorted(surface_results, key=lambda x: x['distance'])
    
    # Consolidate consecutive segments with same surface
    profile = []
    current_surface = sorted_results[0]['surfaceType']
    current_start = 0
    
    for i, result in enumerate(sorted_results):
        if result['surfaceType'] != current_surface:
            # End previous segment
            profile.append({
                'startKm': round(current_start, 2),
                'endKm': round(result['distance'], 2),
                'surface': current_surface
            })
            # Start new segment
            current_surface = result['surfaceType']
            current_start = result['distance']
    
    # Add final segment to end of route
    profile.append({
        'startKm': round(current_start, 2),
        'endKm': round(total_distance, 2),
        'surface': current_surface
    })
    
    return profile


def calculate_surface_percentages(profile, total_distance):
    """Calculate percentage breakdown of surface types."""
    totals = {'road': 0, 'trail': 0, 'technical': 0, 'unknown': 0}
    
    for segment in profile:
        length = segment['endKm'] - segment['startKm']
        surface = segment['surface']
        if surface in totals:
            totals[surface] += length
    
    percentages = {}
    for surface, length in totals.items():
        pct = (length / total_distance * 100) if total_distance > 0 else 0
        if pct > 0:
            percentages[surface] = round(pct, 1)
    
    return percentages


def main():
    parser = argparse.ArgumentParser(description='Analyze GPX surface profile using OSM')
    parser.add_argument('gpx_file', help='Path to GPX file')
    parser.add_argument('--output', choices=['js', 'json'], default='js', 
                       help='Output format (default: js)')
    parser.add_argument('--interval', type=float, default=0.2,
                       help='Sample interval in km (default: 0.2)')
    
    args = parser.parse_args()
    
    print(f'Parsing {args.gpx_file}...')
    points, total_distance = parse_gpx(args.gpx_file)
    print(f'Found {len(points)} points, total distance: {total_distance:.2f} km')
    
    print(f'Sampling every {args.interval} km...')
    samples = sample_points(points, args.interval)
    print(f'Generated {len(samples)} sample points')
    
    print('Building Overpass query...')
    query = build_overpass_query(samples)
    
    print('Querying OSM Overpass API...')
    osm_data = query_overpass(query)
    
    print('Processing OSM ways...')
    ways = process_osm_ways(osm_data)
    print(f'Found {len(ways)} highway ways')
    
    print('Matching points to ways...')
    surface_results = match_points_to_ways(samples, ways)
    
    print('Building surface profile...')
    profile = build_surface_profile(surface_results, total_distance)
    percentages = calculate_surface_percentages(profile, total_distance)
    
    print(f'\n=== Surface Profile ({len(profile)} segments) ===')
    for pct_surface, pct_value in sorted(percentages.items(), key=lambda x: -x[1]):
        print(f'  {pct_surface}: {pct_value}%')
    
    if args.output == 'json':
        output = {
            'totalDistance': round(total_distance, 2),
            'percentages': percentages,
            'surfaceProfile': profile
        }
        print('\n' + json.dumps(output, indent=2))
    else:
        # JavaScript format for races-config.js
        print('\n// Add to races-config.js distanceConfig:')
        print('surfaceProfile: [')
        for i, seg in enumerate(profile):
            comma = ',' if i < len(profile) - 1 else ''
            print(f"    {{ startKm: {seg['startKm']}, endKm: {seg['endKm']}, surface: '{seg['surface']}' }}{comma}")
        print(']')


if __name__ == '__main__':
    main()
