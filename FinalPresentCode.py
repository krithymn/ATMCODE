#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Wind & Weather Avoidance Analysis System - Improved Version
- No manual weather circles (removed fake zones)
- Shows METAR source clearly
- Arrival altitude filtering
- Confidence scoring
- Better visual presentation
"""

import matplotlib.pyplot as plt
import matplotlib.patches as patches
import numpy as np
import requests
import datetime
import json
from math import sin, cos, sqrt, atan2, radians, degrees
import time
import folium
import folium.plugins
import os
import re
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from collections import defaultdict
import pandas as pd
from PIL import Image
import io

# BKK Airport coordinates
BKK_LAT, BKK_LON = 13.6811, 100.7475
BANGKOK_CENTER_LAT, BANGKOK_CENTER_LON = 13.7563, 100.5018

# Bangkok bounds
BANGKOK_BOUNDS = {
    'north': 14.2, 'south': 13.2, 'east': 101.2, 'west': 100.0
}

# Flight tracking bounds
BBOX = {
    "lamin": 13.1, "lamax": 14.3, "lomin": 100.2, "lomax": 101.3
}

# Arrival altitude thresholds
ARRIVAL_ALT_THRESHOLD = 10000  # feet - only analyze flights below this
FINAL_APPROACH_ALT = 3000      # feet - definitely arriving

class RealWeatherRadarAnalyzer:
    """Analyzes actual weather radar data from RainViewer"""
    
    def __init__(self):
        self.radar_cache = {}
        
    def get_tile_coords(self, lat, lon, zoom):
        """Convert lat/lon to tile coordinates"""
        n = 2.0 ** zoom
        x = int((lon + 180.0) / 360.0 * n)
        lat_rad = radians(lat)
        y = int((1.0 - np.arcsinh(np.tan(lat_rad)) / np.pi) / 2.0 * n)
        return x, y
    
    def get_pixel_coords(self, lat, lon, tile_x, tile_y, zoom):
        """Get pixel coordinates within a tile"""
        n = 2.0 ** zoom
        x = (lon + 180.0) / 360.0 * n
        lat_rad = radians(lat)
        y = (1.0 - np.arcsinh(np.tan(lat_rad)) / np.pi) / 2.0 * n
        
        pixel_x = int((x - tile_x) * 256)
        pixel_y = int((y - tile_y) * 256)
        
        return pixel_x, pixel_y
    
    def fetch_radar_tile(self, tile_x, tile_y, zoom, radar_path):
        """Fetch radar tile from RainViewer"""
        cache_key = f"{tile_x}_{tile_y}_{zoom}_{radar_path}"
        
        if cache_key in self.radar_cache:
            return self.radar_cache[cache_key]
        
        url = f"https://tilecache.rainviewer.com{radar_path}/256/{zoom}/{tile_x}/{tile_y}/2/1_1.png"
        
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                img = Image.open(io.BytesIO(response.content))
                self.radar_cache[cache_key] = img
                return img
            else:
                return None
        except Exception as e:
            print(f"Error fetching radar tile: {e}")
            return None
    
    def rgb_to_dbz(self, r, g, b):
        """Convert RGB color to approximate dBZ value"""
        if (r, g, b) == (0, 0, 0) or (r < 10 and g < 10 and b < 10):
            return 0
        
        # RainViewer color scale
        if b > 200 and r < 100:
            if g < 150:
                return 5 + (b - 200) / 55 * 10
            else:
                return 15 + (g - 150) / 105 * 10
        elif g > 200 and r < 150 and b < 150:
            return 25 + (g - 200) / 55 * 10
        elif r > 200 and g > 200 and b < 100:
            return 35 + (255 - b) / 155 * 5
        elif r > 200 and g > 100 and g < 200 and b < 50:
            return 40 + (200 - g) / 100 * 5
        elif r > 200 and g < 100 and b < 100:
            return 45 + (100 - g) / 100 * 10
        elif r > 200 and b > 150 and g < 100:
            return 55 + (b - 150) / 105 * 10
        else:
            brightness = (r + g + b) / 3
            return min(20 + brightness / 255 * 20, 40)
    
    def analyze_weather_at_position(self, lat, lon, radar_path):
        """Analyze weather at specific position using real radar data"""
        zoom = 9
        
        tile_x, tile_y = self.get_tile_coords(lat, lon, zoom)
        img = self.fetch_radar_tile(tile_x, tile_y, zoom, radar_path)
        
        if img is None:
            return {
                'intensity': 0,
                'category': 'NO_DATA',
                'severity': 'UNKNOWN',
                'type': 'No Data',
                'in_weather': False,
                'dbz': 0
            }
        
        px, py = self.get_pixel_coords(lat, lon, tile_x, tile_y, zoom)
        
        if 0 <= px < 256 and 0 <= py < 256:
            if img.mode == 'RGBA':
                r, g, b, a = img.getpixel((px, py))
                if a < 128:
                    dbz = 0
                else:
                    dbz = self.rgb_to_dbz(r, g, b)
            elif img.mode == 'RGB':
                r, g, b = img.getpixel((px, py))
                dbz = self.rgb_to_dbz(r, g, b)
            else:
                img_rgb = img.convert('RGB')
                r, g, b = img_rgb.getpixel((px, py))
                dbz = self.rgb_to_dbz(r, g, b)
        else:
            dbz = 0
        
        # Classify based on dBZ
        if dbz >= 50:
            category = 'HEAVY'
            severity = 'HIGH'
            weather_type = 'Heavy Rain/Thunderstorm'
        elif dbz >= 35:
            category = 'MODERATE'
            severity = 'MEDIUM'
            weather_type = 'Moderate Rain'
        elif dbz >= 20:
            category = 'LIGHT'
            severity = 'LOW'
            weather_type = 'Light Rain'
        elif dbz >= 5:
            category = 'VERY_LIGHT'
            severity = 'MINIMAL'
            weather_type = 'Drizzle'
        else:
            category = 'CLEAR'
            severity = 'NONE'
            weather_type = 'Clear'
        
        return {
            'intensity': dbz,
            'category': category,
            'severity': severity,
            'type': weather_type,
            'in_weather': dbz > 0,
            'dbz': dbz
        }

class WindWeatherAvoidanceAnalyzer:
    def __init__(self):
        self.flight_data = []
        self.weather_history = []
        self.wind_data = None
        self.metar_raw = ""
        self.metar_station = "VTBS"  # Track which METAR we're using
        self.metar_time = None
        self.avoidance_statistics = defaultdict(lambda: defaultdict(int))
        self.driver = None
        self.weather_analyzer = RealWeatherRadarAnalyzer()
        
        # Setup directories
        self.setup_directories()
        
        # Setup Chrome driver
        self.setup_driver()
        
        # Get initial wind data
        self.update_wind_from_metar()
        
    def setup_directories(self):
        """Create organized folder structure for improved version"""
        today = datetime.datetime.now().strftime('%Y-%m-%d')
        self.base_dir = f"wind_weather_avoidance_IMPROVED/{today}"
        self.html_dir = f"{self.base_dir}/html"
        self.png_dir = f"{self.base_dir}/screenshots"
        self.analysis_dir = f"{self.base_dir}/analysis"
        
        for directory in [self.base_dir, self.html_dir, self.png_dir, self.analysis_dir]:
            os.makedirs(directory, exist_ok=True)
        
        print(f"📁 Output directories created (IMPROVED VERSION):")
        print(f"   - Base: {self.base_dir}")
        print(f"   - HTML: {self.html_dir}")
        print(f"   - Screenshots: {self.png_dir}")
        print(f"   - Analysis: {self.analysis_dir}")
    
    def setup_driver(self):
        """Setup Chrome driver for screenshots"""
        try:
            chrome_options = Options()
            chrome_options.add_argument('--headless')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--window-size=1920,1080')
            
            self.driver = webdriver.Chrome(options=chrome_options)
            print("✅ Chrome driver initialized")
        except Exception as e:
            print(f"❌ Chrome driver setup failed: {str(e)}")
            self.driver = None
    
    def parse_metar_wind(self, metar_text):
        """Parse wind information from METAR text"""
        wind_pattern = r'(\d{3}|VRB)(\d{2,3})(G(\d{2,3}))?KT'
        
        match = re.search(wind_pattern, metar_text)
        if match:
            direction = match.group(1)
            speed = int(match.group(2))
            gust = int(match.group(4)) if match.group(4) else None
            
            if direction == 'VRB':
                direction = 0
            else:
                direction = int(direction)
            
            return {
                'direction': direction,
                'speed_kt': speed,
                'gust_kt': gust
            }
        
        if 'CALM' in metar_text or '00000KT' in metar_text:
            return {
                'direction': 0,
                'speed_kt': 0,
                'gust_kt': None
            }
        
        return None
    
    def update_wind_from_metar(self):
        """Fetch and parse wind data from VTBS METAR"""
        url = f"https://aviationweather.gov/api/data/metar?ids={self.metar_station}&format=json&taf=false"
        
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                
                if data and len(data) > 0:
                    metar_data = data[0]
                    self.metar_raw = metar_data.get('rawOb', '')
                    self.metar_time = metar_data.get('reportTime', '')
                    
                    wind_info = self.parse_metar_wind(self.metar_raw)
                    
                    if wind_info:
                        speed_mps = wind_info['speed_kt'] * 0.514444
                        gust_mps = wind_info['gust_kt'] * 0.514444 if wind_info['gust_kt'] else None
                        
                        self.wind_data = {
                            "surface": {
                                "speed_mps": speed_mps,
                                "speed_kt": wind_info['speed_kt'],
                                "direction": wind_info['direction'],
                                "gust_mps": gust_mps,
                                "gust_kt": wind_info['gust_kt'],
                                "timestamp": datetime.datetime.now(),
                                "metar_time": self.metar_time,
                                "raw_metar": self.metar_raw,
                                "station": self.metar_station
                            }
                        }
                        
                        print(f"\n🌬️ METAR Wind Data from {self.metar_station}:")
                        print(f"   Time: {self.metar_time}")
                        print(f"   Wind: {wind_info['speed_kt']} kt from {wind_info['direction']}°")
                        if wind_info['gust_kt']:
                            print(f"   Gusts: {wind_info['gust_kt']} kt")
                        print(f"   Full METAR: {self.metar_raw}")
                        
                        return True
                else:
                    print(f"❌ No METAR data received from {self.metar_station}")
                    
        except Exception as e:
            print(f"❌ Error fetching METAR from {self.metar_station}: {str(e)}")
        
        # Fallback
        print(f"⚠️ Using default wind data (METAR unavailable)")
        self.wind_data = {
            "surface": {
                "speed_mps": 5.2,
                "speed_kt": 10,
                "direction": 230,
                "gust_mps": None,
                "gust_kt": None,
                "timestamp": datetime.datetime.now(),
                "raw_metar": "NO METAR DATA AVAILABLE",
                "station": "DEFAULT"
            }
        }
        return False
    
    def get_weather_history(self, hours_back=2):
        """Get weather radar history"""
        print("🌦️ Fetching weather radar history...")
        
        try:
            url = "https://api.rainviewer.com/public/weather-maps.json"
            response = requests.get(url, timeout=30)
            data = response.json()
            
            all_frames = data.get("radar", {}).get("past", [])
            
            if not all_frames:
                print("❌ No radar history available")
                return []
            
            now = datetime.datetime.now()
            cutoff_time = int((now - datetime.timedelta(hours=hours_back)).timestamp())
            
            recent_frames = [frame for frame in all_frames if frame['time'] >= cutoff_time]
            
            weather_history = []
            for frame in recent_frames:
                frame_time = datetime.datetime.fromtimestamp(frame['time'])
                weather_history.append({
                    'path': frame['path'],
                    'timestamp': frame['time'],
                    'datetime': frame_time,
                    'time_str': frame_time.strftime('%Y-%m-%d %H:%M:%S'),
                    'age_minutes': (now - frame_time).total_seconds() / 60
                })
            
            weather_history.sort(key=lambda x: x['timestamp'], reverse=True)
            self.weather_history = weather_history
            
            print(f"✅ Got {len(weather_history)} weather frames")
            if weather_history:
                print(f"   Latest: {weather_history[0]['time_str']} ({weather_history[0]['age_minutes']:.1f} min ago)")
            
            return weather_history
            
        except Exception as e:
            print(f"❌ Error fetching weather: {str(e)}")
            return []
    
    def get_flights_near_bkk(self):
        """Fetch flights from OpenSky Network"""
        url = "https://opensky-network.org/api/states/all"
        try:
            response = requests.get(url, params=BBOX, timeout=30)
            if response.status_code == 200:
                data = response.json()
                flights = data.get("states", [])
                print(f"✈️ Found {len(flights)} total flights in area")
                return flights
            else:
                print(f"❌ Failed to fetch flight data: {response.status_code}")
                return []
        except Exception as e:
            print(f"❌ Error fetching flight data: {str(e)}")
            return []
    
    def calculate_distance(self, lat1, lon1, lat2, lon2):
        """Calculate distance in km"""
        R = 6371.0
        lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
        dlon = lon2 - lon1
        dlat = lat2 - lat1
        a = sin(dlat/2)**2 + cos(lat1)*cos(lat2)*sin(dlon/2)**2
        c = 2 * atan2(sqrt(a), sqrt(1-a))
        return R * c
    
    def calculate_heading(self, lat1, lon1, lat2, lon2):
        """Calculate heading from point 1 to point 2"""
        lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
        
        dlon = lon2 - lon1
        x = sin(dlon) * cos(lat2)
        y = cos(lat1) * sin(lat2) - sin(lat1) * cos(lat2) * cos(dlon)
        
        initial_bearing = atan2(x, y)
        initial_bearing = degrees(initial_bearing)
        compass_bearing = (initial_bearing + 360) % 360
        
        return compass_bearing
    
    def calculate_wind_component(self, flight_heading, wind_direction, wind_speed):
        """Calculate wind components"""
        flight_heading_rad = radians(flight_heading)
        wind_direction_rad = radians(wind_direction)
        
        relative_wind = wind_direction_rad - flight_heading_rad
        
        headwind_component = wind_speed * cos(relative_wind)
        crosswind_component = abs(wind_speed * sin(relative_wind))
        
        return headwind_component, crosswind_component
    
    def analyze_weather_intensity(self, lat, lon):
        """Analyze REAL weather intensity at position using radar data"""
        if not self.weather_history:
            return {
                'intensity': 0,
                'category': 'NO_DATA',
                'severity': 'UNKNOWN',
                'type': 'No Weather Data',
                'in_weather': False,
                'dbz': 0
            }
        
        latest_frame = self.weather_history[0]
        return self.weather_analyzer.analyze_weather_at_position(
            lat, lon, latest_frame['path']
        )
    
    def calculate_confidence_score(self, flight_info):
        """Calculate confidence score for analysis"""
        confidence = 100.0
        reasons = []
        
        # Check heading/track data quality
        if flight_info.get('track') is None:
            confidence -= 30
            reasons.append("No heading data (-30%)")
        
        # Check weather data age
        if self.weather_history:
            weather_age = self.weather_history[0]['age_minutes']
            if weather_age > 15:
                confidence -= 20
                reasons.append(f"Old weather data ({weather_age:.0f}min, -20%)")
            elif weather_age > 10:
                confidence -= 10
                reasons.append(f"Weather data {weather_age:.0f}min old (-10%)")
        else:
            confidence -= 40
            reasons.append("No weather data (-40%)")
        
        # Check altitude
        altitude_ft = flight_info.get('altitude_ft', 0)
        if altitude_ft > 8000:
            confidence -= 15
            reasons.append(f"High altitude ({altitude_ft}ft, -15%)")
        elif altitude_ft > 5000:
            confidence -= 10
            reasons.append(f"Medium altitude ({altitude_ft}ft, -10%)")
        
        # Check distance to airport
        distance = flight_info.get('distance_km', 0)
        if distance > 60:
            confidence -= 10
            reasons.append(f"Far from airport ({distance:.0f}km, -10%)")
        
        # Ensure confidence doesn't go below 0
        confidence = max(0, confidence)
        
        return {
            'score': confidence,
            'reasons': reasons,
            'quality': 'HIGH' if confidence >= 80 else 'MEDIUM' if confidence >= 60 else 'LOW'
        }
    
    def is_arrival_flight(self, flight):
        """Check if flight is arriving - with altitude filtering"""
        lat, lon, altitude = flight[6], flight[5], flight[7]
        vertical_rate = flight[11]
        
        if not all([lat, lon, altitude]):
            return False
        
        distance = self.calculate_distance(lat, lon, BKK_LAT, BKK_LON)
        altitude_ft = altitude * 3.28084 if altitude else 0
        
        # Strict arrival criteria
        is_low_altitude = altitude_ft < ARRIVAL_ALT_THRESHOLD
        is_within_approach_distance = distance < 80
        is_descending = vertical_rate is not None and vertical_rate < -1.0
        is_final_approach = altitude_ft < FINAL_APPROACH_ALT and distance < 30
        
        # Must be below arrival altitude threshold
        if not is_low_altitude:
            return False
        
        return is_within_approach_distance and (is_descending or is_final_approach)
    
    def process_flights_with_avoidance_analysis(self):
        """Process flights with altitude filtering and confidence scoring"""
        all_flights = self.get_flights_near_bkk()
        self.flight_data = []
        
        arrival_count = 0
        high_altitude_filtered = 0
        
        for flight in all_flights:
            if not flight or len(flight) < 12:
                continue
            
            # Check altitude before processing
            altitude = flight[7]
            altitude_ft = altitude * 3.28084 if altitude else 0
            
            if altitude_ft > ARRIVAL_ALT_THRESHOLD:
                high_altitude_filtered += 1
                continue
            
            if not self.is_arrival_flight(flight):
                continue
            
            arrival_count += 1
            
            lat, lon = flight[6], flight[5]
            callsign = flight[1].strip() if flight[1] else "Unknown"
            velocity = flight[9]
            track = flight[10]
            vertical_rate = flight[11]
            
            # Calculate heading to BKK
            heading_to_bkk = self.calculate_heading(lat, lon, BKK_LAT, BKK_LON)
            
            # Calculate wind components
            headwind, crosswind = self.calculate_wind_component(
                heading_to_bkk,
                self.wind_data["surface"]["direction"],
                self.wind_data["surface"]["speed_mps"]
            )
            
            # Determine wind condition
            if abs(crosswind) > abs(headwind):
                if crosswind > 5:
                    wind_condition = "STRONG_CROSSWIND"
                    wind_category = "CROSSWIND"
                else:
                    wind_condition = "MODERATE_CROSSWIND"
                    wind_category = "CROSSWIND"
            elif headwind > 2:
                if headwind > 5:
                    wind_condition = "STRONG_HEADWIND"
                else:
                    wind_condition = "MODERATE_HEADWIND"
                wind_category = "HEADWIND"
            elif headwind < -2:
                if headwind < -5:
                    wind_condition = "STRONG_TAILWIND"
                else:
                    wind_condition = "MODERATE_TAILWIND"
                wind_category = "TAILWIND"
            else:
                wind_condition = "CALM"
                wind_category = "CALM"
            
            # Analyze REAL weather at flight position
            weather_analysis = self.analyze_weather_intensity(lat, lon)
            
            # Check heading deviation
            if track is not None:
                heading_deviation = abs(track - heading_to_bkk)
                if heading_deviation > 180:
                    heading_deviation = 360 - heading_deviation
            else:
                heading_deviation = 0
            
            # Analyze avoidance
            distance_to_bkk = self.calculate_distance(lat, lon, BKK_LAT, BKK_LON)
            is_avoiding = False
            avoidance_reason = "NONE"
            
            if weather_analysis['in_weather'] and weather_analysis['severity'] in ['HIGH', 'MEDIUM']:
                if heading_deviation > 20 and track is not None:
                    is_avoiding = True
                    avoidance_reason = f"WEATHER_{weather_analysis['severity']}_DEVIATION"
                elif distance_to_bkk > 40 and altitude_ft > 2000:
                    if weather_analysis['severity'] == 'HIGH' and heading_deviation > 10:
                        is_avoiding = True
                        avoidance_reason = "WEATHER_HIGH_PRECAUTION"
            
            flight_info = {
                "callsign": callsign,
                "lat": lat,
                "lon": lon,
                "altitude_ft": int(altitude_ft),
                "speed_kts": int(velocity * 1.94384) if velocity else 0,
                "track": track,
                "vertical_rate": vertical_rate,
                "distance_km": distance_to_bkk,
                "heading_to_bkk": heading_to_bkk,
                "heading_deviation": heading_deviation,
                "headwind_component": headwind,
                "crosswind_component": crosswind,
                "wind_condition": wind_condition,
                "wind_category": wind_category,
                "weather_intensity": weather_analysis['intensity'],
                "weather_dbz": weather_analysis.get('dbz', 0),
                "weather_category": weather_analysis['category'],
                "weather_severity": weather_analysis['severity'],
                "weather_type": weather_analysis['type'],
                "in_weather": weather_analysis['in_weather'],
                "is_avoiding": is_avoiding,
                "avoidance_reason": avoidance_reason
            }
            
            # Calculate confidence score
            confidence_data = self.calculate_confidence_score(flight_info)
            flight_info.update({
                "confidence_score": confidence_data['score'],
                "confidence_quality": confidence_data['quality'],
                "confidence_reasons": confidence_data['reasons']
            })
            
            self.flight_data.append(flight_info)
            
            # Update statistics
            self.avoidance_statistics[wind_category]['total'] += 1
            if is_avoiding:
                self.avoidance_statistics[wind_category]['avoiding'] += 1
            if weather_analysis['in_weather']:
                self.avoidance_statistics[wind_category]['in_weather'] += 1
        
        print(f"✅ Processed {arrival_count} arrival flights (filtered {high_altitude_filtered} high altitude)")
        print(f"   Below {ARRIVAL_ALT_THRESHOLD}ft: {arrival_count} flights")
        return self.flight_data
    
    def calculate_avoidance_percentages(self):
        """Calculate avoidance percentages by wind condition"""
        results = {}
        
        for wind_category, stats in self.avoidance_statistics.items():
            total = stats['total']
            if total > 0:
                avoiding = stats['avoiding']
                in_weather = stats['in_weather']
                
                avoidance_percentage = (avoiding / total) * 100 if total > 0 else 0
                weather_encounter_percentage = (in_weather / total) * 100 if total > 0 else 0
                
                results[wind_category] = {
                    'total_flights': total,
                    'avoiding_weather': avoiding,
                    'in_weather': in_weather,
                    'avoidance_percentage': avoidance_percentage,
                    'weather_encounter_percentage': weather_encounter_percentage
                }
        
        return results
    
    def create_avoidance_analysis_map(self):
        """Create enhanced map with confidence scores and METAR info"""
        current_time = datetime.datetime.now()
        timestamp = current_time.strftime('%Y%m%d_%H%M%S')
        
        # Create map centered on Bangkok area
        m = folium.Map(
            location=[BKK_LAT, BKK_LON],
            zoom_start=10,
            tiles='OpenStreetMap'
        )
        
        # Add REAL weather radar overlay
        if self.weather_history:
            latest_weather = self.weather_history[0]
            radar_layer = folium.raster_layers.TileLayer(
                tiles=f"https://tilecache.rainviewer.com{latest_weather['path']}/256/{{z}}/{{x}}/{{y}}/2/1_1.png",
                attr="RainViewer Real-Time Radar",
                name="Weather Radar (Real)",
                overlay=True,
                control=True,
                opacity=0.7
            )
            radar_layer.add_to(m)
            
            print(f"🌦️ Added real weather radar from: {latest_weather['time_str']}")
        
        # NO FAKE WEATHER CIRCLES - Using real radar only
        
        # Add range circles around BKK (for reference only)
        for radius_km in [20, 40, 60, 80]:
            folium.Circle(
                location=[BKK_LAT, BKK_LON],
                radius=radius_km * 1000,
                color='gray',
                fill=False,
                weight=1,
                opacity=0.3,
                dash_array='5,10'
            ).add_to(m)
        
        # Add flight markers with enhanced information
        for flight in self.flight_data:
            # Color based on confidence and behavior
            if flight['confidence_quality'] == 'LOW':
                opacity = 0.5
            elif flight['confidence_quality'] == 'MEDIUM':
                opacity = 0.7
            else:
                opacity = 1.0
            
            # Icon based on weather and avoidance
            if flight['is_avoiding']:
                icon_color = 'red'
                icon_symbol = 'exclamation-triangle'
            elif flight['in_weather'] and flight['weather_severity'] == 'HIGH':
                icon_color = 'darkred'
                icon_symbol = 'bolt'
            elif flight['in_weather'] and flight['weather_severity'] == 'MEDIUM':
                icon_color = 'orange'
                icon_symbol = 'cloud-rain'
            elif flight['in_weather']:
                icon_color = 'yellow'
                icon_symbol = 'cloud'
            else:
                icon_color = 'green'
                icon_symbol = 'plane'
            
            # Create enhanced popup with confidence and METAR info
            track_str = f"{flight['track']:.0f}°" if flight['track'] is not None else "N/A"
            vs_str = f"{flight['vertical_rate']:.0f}" if flight['vertical_rate'] is not None else "N/A"
            
            popup_html = f"""
            <div style="width: 350px; font-family: Arial, sans-serif;">
                <h4 style="margin: 0 0 10px 0; color: #2c3e50;">
                    {flight['callsign']} 
                    <span style="float: right; font-size: 14px; color: {'#27ae60' if flight['confidence_quality'] == 'HIGH' else '#f39c12' if flight['confidence_quality'] == 'MEDIUM' else '#e74c3c'};">
                        Confidence: {flight['confidence_score']:.0f}%
                    </span>
                </h4>
                <hr style="margin: 5px 0;">
                
                <div style="background: #ecf0f1; padding: 8px; margin: 5px 0; border-radius: 5px;">
                    <b>Flight Info:</b><br>
                    • Altitude: <b>{flight['altitude_ft']:,} ft</b> (Arrival threshold: {ARRIVAL_ALT_THRESHOLD:,} ft)<br>
                    • Speed: {flight['speed_kts']} kts | V/S: {vs_str} ft/min<br>
                    • Distance to BKK: {flight['distance_km']:.1f} km<br>
                    • Track: {track_str} | Ideal: {flight['heading_to_bkk']:.0f}°<br>
                    • Deviation: {flight['heading_deviation']:.1f}°
                </div>
                
                <div style="background: #e8f5e9; padding: 8px; margin: 5px 0; border-radius: 5px;">
                    <b>Wind Analysis (METAR {self.metar_station}):</b><br>
                    • Surface Wind: {self.wind_data['surface']['speed_kt']} kt from {self.wind_data['surface']['direction']}°<br>
                    • Condition: <span style="font-weight: bold; color: #1976d2;">{flight['wind_condition']}</span><br>
                    • Headwind: {flight['headwind_component']:.1f} m/s<br>
                    • Crosswind: {flight['crosswind_component']:.1f} m/s
                </div>
                
                <div style="background: {'#ffebee' if flight['in_weather'] else '#f1f8e9'}; padding: 8px; margin: 5px 0; border-radius: 5px;">
                    <b>Real Weather Radar:</b><br>
                    • Intensity: <b>{flight['weather_dbz']:.1f} dBZ</b><br>
                    • Category: <span style="font-weight: bold; color: {'#d32f2f' if flight['weather_severity'] == 'HIGH' else '#f57c00' if flight['weather_severity'] == 'MEDIUM' else '#388e3c'};">{flight['weather_category']}</span><br>
                    • Type: {flight['weather_type']}<br>
                    • In Weather: <b>{'YES' if flight['in_weather'] else 'NO'}</b>
                </div>
                
                <div style="background: #fff3e0; padding: 8px; margin: 5px 0; border-radius: 5px;">
                    <b>Avoidance Analysis:</b><br>
                    • Avoiding: <b style="color: {'#d32f2f' if flight['is_avoiding'] else '#388e3c'};">{'YES' if flight['is_avoiding'] else 'NO'}</b><br>
                    {f"• Reason: {flight['avoidance_reason']}<br>" if flight['is_avoiding'] else ""}
                    • Analysis Quality: <span style="color: {'#27ae60' if flight['confidence_quality'] == 'HIGH' else '#f39c12' if flight['confidence_quality'] == 'MEDIUM' else '#e74c3c'};">{flight['confidence_quality']}</span>
                </div>
                
                <div style="background: #f5f5f5; padding: 5px; margin: 5px 0; border-radius: 5px; font-size: 11px;">
                    <b>Confidence Factors:</b><br>
                    {"<br>".join(f"• {reason}" for reason in flight['confidence_reasons'])}
                </div>
            </div>
            """
            
            # Create marker with confidence-based opacity
            folium.Marker(
                [flight["lat"], flight["lon"]],
                popup=folium.Popup(popup_html, max_width=400),
                tooltip=f"{flight['callsign']} - {flight['wind_category']} - {flight['weather_dbz']:.0f}dBZ - Conf: {flight['confidence_score']:.0f}%",
                icon=folium.Icon(color=icon_color, icon=icon_symbol, prefix='fa'),
                opacity=opacity
            ).add_to(m)
            
            # Add flight path line to BKK
            if flight['is_avoiding'] and flight['confidence_quality'] != 'LOW':
                line_color = 'red'
                line_dash = '5, 10'
                line_weight = 3
            elif flight['in_weather']:
                line_color = 'orange'
                line_dash = '2, 5'
                line_weight = 2
            else:
                line_color = 'blue'
                line_dash = None
                line_weight = 2
            
            # Make lines more transparent for low confidence
            line_opacity = 0.6 if flight['confidence_quality'] == 'HIGH' else 0.4 if flight['confidence_quality'] == 'MEDIUM' else 0.2
            
            folium.PolyLine(
                [[flight["lat"], flight["lon"]], [BKK_LAT, BKK_LON]],
                color=line_color,
                weight=line_weight,
                opacity=line_opacity,
                dash_array=line_dash
            ).add_to(m)
        
        # Add BKK Airport with METAR info
        metar_popup = f"""
        <div style="width: 300px;">
            <h4>Suvarnabhumi Airport (BKK)</h4>
            <hr>
            <b>METAR Station: {self.metar_station}</b><br>
            <b>Time:</b> {self.metar_time if self.metar_time else 'N/A'}<br>
            <b>Wind:</b> {self.wind_data['surface']['speed_kt']} kt from {self.wind_data['surface']['direction']}°<br>
            {f"<b>Gusts:</b> {self.wind_data['surface']['gust_kt']} kt<br>" if self.wind_data['surface']['gust_kt'] else ""}
            <hr>
            <b>Full METAR:</b><br>
            <span style="font-family: monospace; font-size: 12px;">{self.metar_raw}</span>
        </div>
        """
        
        folium.Marker(
            [BKK_LAT, BKK_LON],
            popup=folium.Popup(metar_popup, max_width=350),
            tooltip=f"BKK - METAR: {self.metar_station}",
            icon=folium.Icon(color='red', icon='star', prefix='fa')
        ).add_to(m)
        
        # Calculate statistics
        stats = self.calculate_avoidance_percentages()
        
        # Add enhanced title with METAR and confidence info
        title_html = f"""
        <div style="position: fixed; top: 10px; left: 50%; transform: translateX(-50%);
                    background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%); 
                    color: white; padding: 20px;
                    border-radius: 10px; z-index: 1000; text-align: center;
                    box-shadow: 0 4px 15px rgba(0,0,0,0.3); min-width: 700px;">
            <h3 style="margin: 0 0 10px 0; font-size: 20px;">🌦️ Wind & Weather Avoidance Analysis</h3>
            <p style="margin: 5px 0; font-size: 14px;">📅 {current_time.strftime('%Y-%m-%d %H:%M:%S')}</p>
            
            <div style="background: rgba(255,255,255,0.1); padding: 8px; border-radius: 5px; margin: 10px 0;">
                <span style="font-size: 13px;">
                    📡 METAR: <b>{self.metar_station}</b> | 
                    🌬️ Wind: <b>{self.wind_data['surface']['speed_kt']}kt/{self.wind_data['surface']['direction']}°</b> | 
                    ⬇️ Altitude Filter: <b>≤{ARRIVAL_ALT_THRESHOLD:,}ft</b>
                </span>
            </div>
            
            <div style="margin-top: 10px; font-size: 13px; display: flex; justify-content: center; gap: 15px;">
        """
        
        for category in ['HEADWIND', 'TAILWIND', 'CROSSWIND', 'CALM']:
            if category in stats:
                data = stats[category]
                color = {'HEADWIND': '#ff6b6b', 'TAILWIND': '#51cf66', 'CROSSWIND': '#339af0', 'CALM': '#868e96'}.get(category, '#fff')
                title_html += f"""
                    <div style="background: rgba(255,255,255,0.15); padding: 5px 10px; border-radius: 5px;">
                        <span style="color: {color}; font-weight: bold;">{category}:</span><br>
                        {data['avoidance_percentage']:.1f}% avoiding
                        ({data['avoiding_weather']}/{data['total_flights']})
                    </div>
                """
        
        # Add average confidence score
        if self.flight_data:
            avg_confidence = sum(f['confidence_score'] for f in self.flight_data) / len(self.flight_data)
            high_conf_count = sum(1 for f in self.flight_data if f['confidence_quality'] == 'HIGH')
            
            title_html += f"""
            </div>
            <div style="margin-top: 10px; font-size: 11px; opacity: 0.9;">
                📊 Avg Confidence: <b>{avg_confidence:.0f}%</b> | 
                High Quality: <b>{high_conf_count}/{len(self.flight_data)}</b> flights | 
                🌦️ Weather Age: <b>{self.weather_history[0]['age_minutes']:.0f}min</b>
            </div>
        </div>
        """
        else:
            title_html += """
            </div>
        </div>
        """
        
        m.get_root().html.add_child(folium.Element(title_html))
        
        # Add enhanced legend with confidence info
        legend_html = """
        <div style="position: fixed; bottom: 20px; right: 20px; 
                    background: white; padding: 15px; border: 2px solid #2c3e50;
                    border-radius: 8px; z-index: 1000; box-shadow: 0 2px 10px rgba(0,0,0,0.2);">
            <b style="font-size: 14px; color: #2c3e50;">Legend:</b><br>
            <div style="margin-top: 8px; font-size: 12px;">
                <b>Flight Status:</b><br>
                <div style="margin: 3px 0;">🔴 Avoiding Weather</div>
                <div style="margin: 3px 0;">⚡ In Heavy Weather</div>
                <div style="margin: 3px 0;">🌧️ In Moderate Weather</div>
                <div style="margin: 3px 0;">☁️ In Light Weather</div>
                <div style="margin: 3px 0;">✈️ Clear Path</div>
                <hr style="margin: 8px 0;">
                <b>Line Types:</b><br>
                <div style="margin: 3px 0;">--- Avoidance Route</div>
                <div style="margin: 3px 0;">─ Direct Route</div>
                <hr style="margin: 8px 0;">
                <b>Confidence Quality:</b><br>
                <div style="margin: 3px 0;">🟢 High (80-100%)</div>
                <div style="margin: 3px 0;">🟡 Medium (60-79%)</div>
                <div style="margin: 3px 0;">🔴 Low (<60%)</div>
                <hr style="margin: 8px 0;">
                <div style="font-size: 11px; color: #666;">
                    Weather: Real radar data<br>
                    No simulated zones
                </div>
            </div>
        </div>
        """
        m.get_root().html.add_child(folium.Element(legend_html))
        
        # Save map
        html_filename = f"{self.html_dir}/improved_analysis_{timestamp}.html"
        m.save(html_filename)
        
        print(f"💾 Saved improved analysis map: {html_filename}")
        
        # Take screenshot if driver available
        if self.driver:
            png_filename = f"{self.png_dir}/improved_analysis_{timestamp}.png"
            self.capture_screenshot(html_filename, png_filename)
        
        return html_filename
    
    def capture_screenshot(self, html_file, png_file):
        """Capture screenshot of HTML map"""
        try:
            file_url = f"file://{os.path.abspath(html_file)}"
            self.driver.get(file_url)
            
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CLASS_NAME, "leaflet-container"))
            )
            
            time.sleep(3)
            self.driver.save_screenshot(png_file)
            print(f"📸 Saved screenshot: {png_file}")
            
        except Exception as e:
            print(f"❌ Screenshot failed: {str(e)}")
    
    def create_analysis_report(self):
        """Create detailed analysis report with improvements"""
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        report_file = f"{self.analysis_dir}/improved_report_{timestamp}.txt"
        
        stats = self.calculate_avoidance_percentages()
        
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write("="*80 + "\n")
            f.write("WIND & WEATHER AVOIDANCE ANALYSIS REPORT - IMPROVED VERSION\n")
            f.write("="*80 + "\n\n")
            
            f.write(f"Report Generated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Analysis Type: Real Weather Radar Data (No Simulated Zones)\n\n")
            
            f.write("DATA SOURCES\n")
            f.write("-"*40 + "\n")
            f.write(f"METAR Station: {self.metar_station}\n")
            f.write(f"METAR Time: {self.metar_time if self.metar_time else 'N/A'}\n")
            f.write(f"Wind: {self.wind_data['surface']['speed_kt']} kt from {self.wind_data['surface']['direction']}°\n")
            if self.wind_data['surface']['gust_kt']:
                f.write(f"Gusts: {self.wind_data['surface']['gust_kt']} kt\n")
            f.write(f"Full METAR: {self.metar_raw}\n\n")
            
            if self.weather_history:
                f.write(f"Weather Radar: {self.weather_history[0]['time_str']} ({self.weather_history[0]['age_minutes']:.1f} min ago)\n")
                f.write(f"Radar Source: RainViewer API\n\n")
            
            f.write("ALTITUDE FILTERING\n")
            f.write("-"*40 + "\n")
            f.write(f"Maximum Altitude for Analysis: {ARRIVAL_ALT_THRESHOLD:,} ft\n")
            f.write(f"Final Approach Altitude: {FINAL_APPROACH_ALT:,} ft\n")
            f.write(f"Only analyzing arrival flights below threshold\n\n")
            
            f.write("EXECUTIVE SUMMARY\n")
            f.write("-"*40 + "\n")
            f.write(f"Total Arrival Flights Analyzed: {len(self.flight_data)}\n")
            
            if self.flight_data:
                total_avoiding = sum(1 for f in self.flight_data if f['is_avoiding'])
                total_in_weather = sum(1 for f in self.flight_data if f['in_weather'])
                avg_confidence = sum(f['confidence_score'] for f in self.flight_data) / len(self.flight_data)
                high_conf = sum(1 for f in self.flight_data if f['confidence_quality'] == 'HIGH')
                
                f.write(f"Flights Avoiding Weather: {total_avoiding} ({(total_avoiding/len(self.flight_data)*100):.1f}%)\n")
                f.write(f"Flights in Real Weather: {total_in_weather} ({(total_in_weather/len(self.flight_data)*100):.1f}%)\n")
                f.write(f"Average Confidence Score: {avg_confidence:.1f}%\n")
                f.write(f"High Confidence Analyses: {high_conf} ({(high_conf/len(self.flight_data)*100):.1f}%)\n\n")
                
                # Altitude distribution
                f.write("ALTITUDE DISTRIBUTION\n")
                f.write("-"*40 + "\n")
                alt_ranges = [(0, 3000), (3000, 5000), (5000, 7000), (7000, 10000)]
                for min_alt, max_alt in alt_ranges:
                    count = sum(1 for f in self.flight_data if min_alt <= f['altitude_ft'] < max_alt)
                    f.write(f"{min_alt:,}-{max_alt:,} ft: {count} flights\n")
                f.write("\n")
            
            f.write("AVOIDANCE BY WIND CONDITION\n")
            f.write("-"*40 + "\n")
            
            for category in ['HEADWIND', 'TAILWIND', 'CROSSWIND', 'CALM']:
                if category in stats:
                    data = stats[category]
                    f.write(f"\n{category}:\n")
                    f.write(f"  Total Flights: {data['total_flights']}\n")
                    f.write(f"  Avoiding Weather: {data['avoiding_weather']} ({data['avoidance_percentage']:.1f}%)\n")
                    f.write(f"  In Real Weather: {data['in_weather']} ({data['weather_encounter_percentage']:.1f}%)\n")
            
            f.write("\n\nCONFIDENCE ANALYSIS\n")
            f.write("-"*40 + "\n")
            
            if self.flight_data:
                # Group by confidence quality
                conf_groups = {'HIGH': [], 'MEDIUM': [], 'LOW': []}
                for flight in self.flight_data:
                    conf_groups[flight['confidence_quality']].append(flight)
                
                for quality, flights in conf_groups.items():
                    if flights:
                        f.write(f"\n{quality} Confidence ({len(flights)} flights):\n")
                        avg_score = sum(f['confidence_score'] for f in flights) / len(flights)
                        f.write(f"  Average Score: {avg_score:.1f}%\n")
                        
                        # Common issues
                        issues = {}
                        for flight in flights:
                            for reason in flight['confidence_reasons']:
                                if reason not in issues:
                                    issues[reason] = 0
                                issues[reason] += 1
                        
                        f.write("  Common Issues:\n")
                        for issue, count in sorted(issues.items(), key=lambda x: x[1], reverse=True):
                            f.write(f"    - {issue}: {count} flights\n")
            
            f.write("\n\nDETAILED FLIGHT ANALYSIS\n")
            f.write("-"*40 + "\n")
            
            # Show only high-confidence avoiding flights
            high_conf_avoiding = [f for f in self.flight_data if f['is_avoiding'] and f['confidence_quality'] == 'HIGH']
            
            if high_conf_avoiding:
                f.write(f"\nHIGH CONFIDENCE WEATHER AVOIDANCE ({len(high_conf_avoiding)} flights):\n")
                for flight in high_conf_avoiding:
                    f.write(f"\n  ✈️ {flight['callsign']} (Conf: {flight['confidence_score']:.0f}%)\n")
                    f.write(f"     Position: {flight['lat']:.3f}°N, {flight['lon']:.3f}°E\n")
                    f.write(f"     Altitude: {flight['altitude_ft']:,} ft | Distance: {flight['distance_km']:.1f} km\n")
                    f.write(f"     Wind: {flight['wind_category']} ({flight['wind_condition']})\n")
                    f.write(f"     Real Weather: {flight['weather_dbz']:.1f} dBZ - {flight['weather_category']}\n")
                    f.write(f"     Heading Deviation: {flight['heading_deviation']:.1f}°\n")
                    f.write(f"     Reason: {flight['avoidance_reason']}\n")
            
            f.write("\n\nDATA QUALITY NOTES\n")
            f.write("-"*40 + "\n")
            f.write("• Using REAL weather radar data from RainViewer API\n")
            f.write("• NO simulated weather zones or manual circles\n")
            f.write(f"• METAR data from {self.metar_station} station\n")
            f.write(f"• Altitude filtering applied (≤{ARRIVAL_ALT_THRESHOLD:,} ft)\n")
            f.write("• Confidence scoring considers data quality factors\n")
            f.write("• Weather intensity measured in actual dBZ values\n")
        
        print(f"📄 Improved analysis report saved: {report_file}")
        return report_file
    
    def create_statistics_chart(self):
        """Create enhanced statistics chart with confidence data"""
        stats = self.calculate_avoidance_percentages()
        
        if not stats or not self.flight_data:
            print("❌ No data for statistics chart")
            return None
        
        # Prepare data
        categories = list(stats.keys())
        avoidance_percentages = [stats[cat]['avoidance_percentage'] for cat in categories]
        weather_percentages = [stats[cat]['weather_encounter_percentage'] for cat in categories]
        total_flights = [stats[cat]['total_flights'] for cat in categories]
        
        # Create figure with subplots
        fig = plt.figure(figsize=(16, 12))
        
        # Add main title with METAR info
        fig.suptitle(f'Wind & Weather Avoidance Analysis - Improved Version\n'
                     f'METAR {self.metar_station}: {self.wind_data["surface"]["speed_kt"]}kt/{self.wind_data["surface"]["direction"]}° | '
                     f'Altitude Filter: ≤{ARRIVAL_ALT_THRESHOLD:,}ft', 
                     fontsize=16)
        
        # Create 6 subplots
        ax1 = plt.subplot(2, 3, 1)
        ax2 = plt.subplot(2, 3, 2)
        ax3 = plt.subplot(2, 3, 3)
        ax4 = plt.subplot(2, 3, 4)
        ax5 = plt.subplot(2, 3, 5)
        ax6 = plt.subplot(2, 3, 6)
        
        # Color scheme
        colors = {'HEADWIND': '#e74c3c', 'TAILWIND': '#27ae60', 'CROSSWIND': '#3498db', 'CALM': '#95a5a6'}
        bar_colors = [colors.get(cat, 'gray') for cat in categories]
        
        # 1. Avoidance percentages
        bars1 = ax1.bar(categories, avoidance_percentages, color=bar_colors, alpha=0.8)
        ax1.set_ylabel('Avoidance Percentage (%)')
        ax1.set_title('Weather Avoidance by Wind Condition')
        ax1.set_ylim(0, max(avoidance_percentages + [20]) * 1.2)
        
        for bar, percentage in zip(bars1, avoidance_percentages):
            height = bar.get_height()
            ax1.text(bar.get_x() + bar.get_width()/2., height,
                    f'{percentage:.1f}%',
                    ha='center', va='bottom')
        
        # 2. Weather encounters
        bars2 = ax2.bar(categories, weather_percentages, color=bar_colors, alpha=0.6)
        ax2.set_ylabel('Weather Encounter Rate (%)')
        ax2.set_title('Flights Encountering Real Weather')
        ax2.set_ylim(0, max(weather_percentages + [20]) * 1.2)
        
        for bar, percentage in zip(bars2, weather_percentages):
            height = bar.get_height()
            ax2.text(bar.get_x() + bar.get_width()/2., height,
                    f'{percentage:.1f}%',
                    ha='center', va='bottom')
        
        # 3. Flight distribution pie
        ax3.pie(total_flights, labels=categories, autopct='%1.1f%%', 
                colors=[colors.get(cat, 'gray') for cat in categories],
                startangle=90)
        ax3.set_title('Flight Distribution by Wind Condition')
        
        # 4. Confidence distribution
        conf_counts = {'HIGH': 0, 'MEDIUM': 0, 'LOW': 0}
        for flight in self.flight_data:
            conf_counts[flight['confidence_quality']] += 1
        
        conf_labels = list(conf_counts.keys())
        conf_values = list(conf_counts.values())
        conf_colors = ['#27ae60', '#f39c12', '#e74c3c']
        
        ax4.pie(conf_values, labels=conf_labels, autopct='%1.0f%%',
                colors=conf_colors, startangle=90)
        ax4.set_title('Analysis Confidence Distribution')
        
        # 5. Altitude distribution
        altitudes = [f['altitude_ft'] for f in self.flight_data]
        ax5.hist(altitudes, bins=20, color='steelblue', alpha=0.7, edgecolor='black')
        ax5.set_xlabel('Altitude (ft)')
        ax5.set_ylabel('Number of Flights')
        ax5.set_title('Arrival Flight Altitude Distribution')
        ax5.axvline(x=FINAL_APPROACH_ALT, color='red', linestyle='--', label='Final Approach')
        ax5.axvline(x=ARRIVAL_ALT_THRESHOLD, color='orange', linestyle='--', label='Analysis Limit')
        ax5.legend()
        
        # 6. Weather intensity vs confidence
        weather_dbz = [f['weather_dbz'] for f in self.flight_data if f['in_weather']]
        confidence_scores = [f['confidence_score'] for f in self.flight_data if f['in_weather']]
        
        if weather_dbz and confidence_scores:
            ax6.scatter(weather_dbz, confidence_scores, alpha=0.6, c='darkblue')
            ax6.set_xlabel('Weather Intensity (dBZ)')
            ax6.set_ylabel('Confidence Score (%)')
            ax6.set_title('Weather Intensity vs Analysis Confidence')
            ax6.grid(True, alpha=0.3)
        else:
            ax6.text(0.5, 0.5, 'No Weather Encounters', ha='center', va='center', transform=ax6.transAxes)
            ax6.set_title('Weather Intensity vs Confidence')
        
        # Save chart
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        chart_file = f"{self.analysis_dir}/improved_statistics_{timestamp}.png"
        plt.tight_layout()
        plt.savefig(chart_file, dpi=300, bbox_inches='tight')
        plt.close()
        
        print(f"📊 Enhanced statistics chart saved: {chart_file}")
        return chart_file
    
    def run_single_analysis(self):
        """Run a single analysis with all improvements"""
        print("\n🔍 Running Improved Wind & Weather Avoidance Analysis...")
        print("✨ Improvements:")
        print("   - NO manual weather circles (real radar only)")
        print("   - Altitude filtering (arrivals ≤10,000 ft)")
        print("   - Confidence scoring for each analysis")
        print("   - Clear METAR source display")
        print("   - Enhanced visualizations\n")
        
        # Update wind data
        self.update_wind_from_metar()
        
        # Get weather data
        self.get_weather_history()
        
        # Process flights with improvements
        self.process_flights_with_avoidance_analysis()
        
        if self.flight_data:
            # Create outputs
            html_file = self.create_avoidance_analysis_map()
            report_file = self.create_analysis_report()
            chart_file = self.create_statistics_chart()
            
            # Print summary
            self.print_analysis_summary()
            
            print(f"\n✅ Improved analysis complete!")
            print(f"📂 Files saved in: {self.base_dir}")
            
            return {
                'html': html_file,
                'report': report_file,
                'chart': chart_file
            }
        else:
            print("❌ No arrival flights found below altitude threshold")
            return None
    
    def print_analysis_summary(self):
        """Print enhanced analysis summary"""
        stats = self.calculate_avoidance_percentages()
        
        print("\n" + "="*80)
        print("IMPROVED WIND & WEATHER AVOIDANCE ANALYSIS SUMMARY")
        print("="*80)
        
        print(f"\n📊 Overall Statistics:")
        print(f"   Total Arrival Flights (≤{ARRIVAL_ALT_THRESHOLD:,}ft): {len(self.flight_data)}")
        
        if self.flight_data:
            total_avoiding = sum(1 for f in self.flight_data if f['is_avoiding'])
            total_in_weather = sum(1 for f in self.flight_data if f['in_weather'])
            avg_confidence = sum(f['confidence_score'] for f in self.flight_data) / len(self.flight_data)
            high_conf = sum(1 for f in self.flight_data if f['confidence_quality'] == 'HIGH')
            
            print(f"   Avoiding Weather: {total_avoiding} ({(total_avoiding/len(self.flight_data)*100):.1f}%)")
            print(f"   In Real Weather: {total_in_weather} ({(total_in_weather/len(self.flight_data)*100):.1f}%)")
            print(f"   Average Confidence: {avg_confidence:.1f}%")
            print(f"   High Quality Analyses: {high_conf}/{len(self.flight_data)}")
            
            # Weather intensity summary
            if total_in_weather > 0:
                avg_dbz = sum(f['weather_dbz'] for f in self.flight_data if f['in_weather']) / total_in_weather
                max_dbz = max((f['weather_dbz'] for f in self.flight_data if f['in_weather']), default=0)
                print(f"   Average Weather Intensity: {avg_dbz:.1f} dBZ")
                print(f"   Maximum Weather Intensity: {max_dbz:.1f} dBZ")
        
        print(f"\n📡 Data Sources:")
        print(f"   METAR Station: {self.metar_station}")
        print(f"   METAR Time: {self.metar_time if self.metar_time else 'N/A'}")
        print(f"   Wind: {self.wind_data['surface']['speed_kt']} kt from {self.wind_data['surface']['direction']}°")
        if self.weather_history:
            print(f"   Weather Radar: {self.weather_history[0]['age_minutes']:.1f} minutes old")
        
        print(f"\n📈 Avoidance by Wind Type:")
        for category in ['HEADWIND', 'TAILWIND', 'CROSSWIND', 'CALM']:
            if category in stats:
                data = stats[category]
                print(f"   {category}: {data['avoidance_percentage']:.1f}% avoiding ({data['avoiding_weather']}/{data['total_flights']} flights)")
        
        # Confidence breakdown
        if self.flight_data:
            print(f"\n🎯 Confidence Analysis:")
            conf_groups = {'HIGH': 0, 'MEDIUM': 0, 'LOW': 0}
            for flight in self.flight_data:
                conf_groups[flight['confidence_quality']] += 1
            
            for quality, count in conf_groups.items():
                percentage = (count / len(self.flight_data)) * 100
                print(f"   {quality}: {count} flights ({percentage:.1f}%)")
            
            # Common confidence issues
            all_reasons = []
            for flight in self.flight_data:
                all_reasons.extend(flight['confidence_reasons'])
            
            if all_reasons:
                print(f"\n⚠️ Common Confidence Issues:")
                reason_counts = {}
                for reason in all_reasons:
                    reason_counts[reason] = reason_counts.get(reason, 0) + 1
                
                for reason, count in sorted(reason_counts.items(), key=lambda x: x[1], reverse=True)[:3]:
                    print(f"   - {reason}: {count} occurrences")
        
        print("\n💡 Key Improvements in This Version:")
        print("   ✅ Real weather radar only (no fake circles)")
        print("   ✅ Altitude-filtered arrivals only")
        print("   ✅ Confidence scoring for reliability")
        print("   ✅ Clear METAR source identification")
        print("   ✅ Enhanced data quality indicators")
    
    def run_continuous_monitoring(self, interval_minutes=10):
        """Run continuous monitoring with improvements"""
        print(f"\n🔄 Starting IMPROVED continuous monitoring")
        print(f"⏰ Collection interval: {interval_minutes} minutes")
        print("✨ Features: Altitude filtering, confidence scoring, METAR tracking")
        print("Press Ctrl+C to stop\n")
        
        # Reset cumulative statistics
        self.cumulative_stats = defaultdict(lambda: defaultdict(int))
        self.cumulative_confidence = []
        collection_count = 0
        
        try:
            while True:
                collection_count += 1
                print(f"\n{'='*60}")
                print(f"Collection #{collection_count} at {datetime.datetime.now().strftime('%H:%M:%S')}")
                print(f"{'='*60}")
                
                # Reset per-run statistics
                self.avoidance_statistics = defaultdict(lambda: defaultdict(int))
                
                # Run analysis
                results = self.run_single_analysis()
                
                if results and self.flight_data:
                    # Update cumulative statistics
                    for wind_cat, stats in self.avoidance_statistics.items():
                        for stat_type, value in stats.items():
                            self.cumulative_stats[wind_cat][stat_type] += value
                    
                    # Track cumulative confidence
                    avg_conf = sum(f['confidence_score'] for f in self.flight_data) / len(self.flight_data)
                    self.cumulative_confidence.append(avg_conf)
                    
                    # Print cumulative stats
                    print(f"\n📊 Cumulative Statistics (from {collection_count} collections):")
                    for category in ['HEADWIND', 'TAILWIND', 'CROSSWIND', 'CALM']:
                        if category in self.cumulative_stats:
                            total = self.cumulative_stats[category]['total']
                            avoiding = self.cumulative_stats[category]['avoiding']
                            if total > 0:
                                percentage = (avoiding / total) * 100
                                print(f"   {category}: {percentage:.1f}% ({avoiding}/{total})")
                    
                    # Average confidence over time
                    if self.cumulative_confidence:
                        overall_avg_conf = sum(self.cumulative_confidence) / len(self.cumulative_confidence)
                        print(f"\n📈 Average Confidence Score: {overall_avg_conf:.1f}%")
                
                print(f"\nNext collection in {interval_minutes} minutes...")
                time.sleep(interval_minutes * 60)
                
        except KeyboardInterrupt:
            print(f"\n🛑 Monitoring stopped after {collection_count} collections")
            
            # Save final cumulative report
            self.save_cumulative_report(collection_count)
    
    def save_cumulative_report(self, collection_count):
        """Save enhanced cumulative statistics report"""
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        report_file = f"{self.analysis_dir}/cumulative_improved_{timestamp}.txt"
        
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write("="*80 + "\n")
            f.write("CUMULATIVE ANALYSIS REPORT - IMPROVED VERSION\n")
            f.write("="*80 + "\n\n")
            
            f.write(f"Total Collections: {collection_count}\n")
            f.write(f"Report Generated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"METAR Station Used: {self.metar_station}\n")
            f.write(f"Altitude Filter: ≤{ARRIVAL_ALT_THRESHOLD:,} ft\n\n")
            
            f.write("CUMULATIVE STATISTICS BY WIND CONDITION\n")
            f.write("-"*40 + "\n")
            
            for category in ['HEADWIND', 'TAILWIND', 'CROSSWIND', 'CALM']:
                if category in self.cumulative_stats:
                    stats = self.cumulative_stats[category]
                    total = stats['total']
                    avoiding = stats['avoiding']
                    in_weather = stats['in_weather']
                    
                    if total > 0:
                        avoid_pct = (avoiding / total) * 100
                        weather_pct = (in_weather / total) * 100
                        
                        f.write(f"\n{category}:\n")
                        f.write(f"  Total Flights: {total}\n")
                        f.write(f"  Avoided Weather: {avoiding} ({avoid_pct:.1f}%)\n")
                        f.write(f"  Encountered Weather: {in_weather} ({weather_pct:.1f}%)\n")
            
            if self.cumulative_confidence:
                f.write(f"\n\nCONFIDENCE TRENDS\n")
                f.write("-"*40 + "\n")
                f.write(f"Average Confidence: {sum(self.cumulative_confidence)/len(self.cumulative_confidence):.1f}%\n")
                f.write(f"Highest Collection Confidence: {max(self.cumulative_confidence):.1f}%\n")
                f.write(f"Lowest Collection Confidence: {min(self.cumulative_confidence):.1f}%\n")
            
            f.write(f"\n\nANALYSIS IMPROVEMENTS APPLIED:\n")
            f.write(f"✅ Real weather radar data only (no simulations)\n")
            f.write(f"✅ Altitude filtering for arrivals\n")
            f.write(f"✅ Confidence scoring system\n")
            f.write(f"✅ METAR source tracking\n")
            f.write(f"✅ Enhanced data quality metrics\n")
        
        print(f"\n📄 Cumulative report saved: {report_file}")
    
    def __del__(self):
        """Cleanup"""
        if self.driver:
            self.driver.quit()

def main():
    print("\n" + "="*80)
    print("🌦️ WIND & WEATHER AVOIDANCE ANALYSIS - IMPROVED VERSION")
    print("="*80)
    
    print("\n✨ IMPROVEMENTS IN THIS VERSION:")
    print("   ✅ NO manual weather circles - using real radar only")
    print("   ✅ Altitude filtering - only arrivals ≤10,000 ft")
    print("   ✅ Confidence scoring - know reliability of each analysis")
    print("   ✅ METAR display - shows which station and full data")
    print("   ✅ Enhanced visualizations - 6-panel statistics")
    
    print("\n📊 WHAT THIS SOLVES:")
    print("   • Removes fake weather zones from map")
    print("   • Filters out high-altitude overflights")
    print("   • Shows analysis reliability")
    print("   • Clear data source attribution")
    print("   • Better statistical confidence")
    
    # Check for required libraries
    try:
        import PIL
        print("\n✅ PIL/Pillow installed - Real radar analysis ready")
    except ImportError:
        print("\n⚠️ WARNING: PIL/Pillow not installed!")
        print("   Install with: pip install Pillow")
        response = input("\nContinue anyway? (y/n): ")
        if response.lower() != 'y':
            return
    
    analyzer = WindWeatherAvoidanceAnalyzer()
    
    if not analyzer.driver:
        print("\n⚠️ WARNING: Screenshot capture disabled")
        proceed = input("   Continue with HTML only? (y/n): ")
        if proceed.lower() != 'y':
            return
    
    print("\n📋 Options:")
    print("   1. Single improved analysis")
    print("   2. Continuous monitoring with improvements")
    
    choice = input("\nEnter choice (1 or 2): ")
    
    if choice == "1":
        results = analyzer.run_single_analysis()
        if results:
            print("\n🎯 Check your results:")
            print("   - NO colored circles on the map")
            print("   - Confidence scores in popups")
            print("   - METAR info clearly shown")
            print("   - Only low-altitude arrivals analyzed")
        
    elif choice == "2":
        interval = input("Enter interval in minutes (default 10): ")
        interval = int(interval) if interval.strip() else 10
        if interval < 5:
            print("⚠️ Minimum interval is 5 minutes")
            interval = 5
        analyzer.run_continuous_monitoring(interval)
    else:
        print("❌ Invalid choice")

if __name__ == "__main__":
    main()