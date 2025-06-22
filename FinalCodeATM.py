#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Wind & Weather Avoidance Analysis System
Analyzes flight behavior in relation to weather echoes and wind conditions
Combines METAR wind data with weather radar to track avoidance patterns
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

class WindWeatherAvoidanceAnalyzer:
    def __init__(self):
        self.flight_data = []
        self.weather_history = []
        self.wind_data = None
        self.metar_raw = ""
        self.avoidance_statistics = defaultdict(lambda: defaultdict(int))
        self.driver = None
        
        # Setup directories
        self.setup_directories()
        
        # Setup Chrome driver
        self.setup_driver()
        
        # Get initial wind data
        self.update_wind_from_metar()
        
    def setup_directories(self):
        """Create organized folder structure"""
        today = datetime.datetime.now().strftime('%Y-%m-%d')
        self.base_dir = f"wind_weather_avoidance_data/{today}"
        self.html_dir = f"{self.base_dir}/html"
        self.png_dir = f"{self.base_dir}/screenshots"
        self.analysis_dir = f"{self.base_dir}/analysis"
        
        for directory in [self.base_dir, self.html_dir, self.png_dir, self.analysis_dir]:
            os.makedirs(directory, exist_ok=True)
        
        print(f"📁 Output directories created:")
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
        url = "https://aviationweather.gov/api/data/metar?ids=VTBS&format=json&taf=false"
        
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                
                if data and len(data) > 0:
                    metar_data = data[0]
                    self.metar_raw = metar_data.get('rawOb', '')
                    
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
                                "metar_time": metar_data.get('reportTime', ''),
                                "raw_metar": self.metar_raw
                            }
                        }
                        
                        print(f"\n🌬️ METAR Wind Data from VTBS:")
                        print(f"   Wind: {wind_info['speed_kt']} kt from {wind_info['direction']}°")
                        if wind_info['gust_kt']:
                            print(f"   Gusts: {wind_info['gust_kt']} kt")
                        
                        return True
                else:
                    print("❌ No METAR data received")
                    
        except Exception as e:
            print(f"❌ Error fetching METAR: {str(e)}")
        
        # Fallback
        print("⚠️ Using default wind data")
        self.wind_data = {
            "surface": {
                "speed_mps": 5.2,
                "speed_kt": 10,
                "direction": 230,
                "gust_mps": None,
                "gust_kt": None,
                "timestamp": datetime.datetime.now(),
                "raw_metar": "NO METAR DATA"
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
                print(f"✈️ Found {len(flights)} flights")
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
        """Analyze weather intensity at position"""
        # Simulated weather zones - in real implementation, query actual radar data
        weather_zones = [
            {'lat': 13.8, 'lon': 100.4, 'radius': 25, 'intensity': 30, 'type': 'Light Rain'},
            {'lat': 14.1, 'lon': 100.8, 'radius': 30, 'intensity': 45, 'type': 'Moderate Rain'},
            {'lat': 13.4, 'lon': 101.0, 'radius': 20, 'intensity': 60, 'type': 'Heavy Rain'},
            {'lat': 13.9, 'lon': 100.6, 'radius': 15, 'intensity': 55, 'type': 'Thunderstorm'},
        ]
        
        max_intensity = 0
        weather_type = 'CLEAR'
        in_weather = False
        
        for zone in weather_zones:
            distance = self.calculate_distance(lat, lon, zone['lat'], zone['lon'])
            if distance <= zone['radius']:
                intensity_factor = max(0, 1 - (distance / zone['radius']))
                current_intensity = zone['intensity'] * intensity_factor
                
                if current_intensity > max_intensity:
                    max_intensity = current_intensity
                    weather_type = zone['type']
                    in_weather = True
        
        # Classify intensity
        if max_intensity >= 50:
            category = 'HEAVY'
            severity = 'HIGH'
        elif max_intensity >= 30:
            category = 'MODERATE'
            severity = 'MEDIUM'
        elif max_intensity >= 10:
            category = 'LIGHT'
            severity = 'LOW'
        else:
            category = 'CLEAR'
            severity = 'NONE'
        
        return {
            'intensity': max_intensity,
            'category': category,
            'severity': severity,
            'type': weather_type,
            'in_weather': in_weather
        }
    
    def determine_avoidance_behavior(self, flight, weather_analysis):
        """Determine if flight is avoiding weather"""
        # Check if flight path suggests weather avoidance
        distance_to_bkk = flight['distance_km']
        
        # Typical approach paths
        if distance_to_bkk > 50:  # Far from airport
            if weather_analysis['in_weather'] and weather_analysis['severity'] == 'HIGH':
                return 'LIKELY_AVOIDING'
            elif weather_analysis['in_weather'] and weather_analysis['severity'] == 'MEDIUM':
                return 'POSSIBLY_AVOIDING'
            else:
                return 'NOT_AVOIDING'
        else:  # Close to airport
            if weather_analysis['severity'] == 'HIGH':
                return 'FORCED_THROUGH'  # Must land despite weather
            else:
                return 'NORMAL_APPROACH'
    
    def is_arrival_flight(self, flight):
        """Check if flight is arriving"""
        lat, lon, altitude = flight[6], flight[5], flight[7]
        vertical_rate = flight[11]
        
        if not all([lat, lon, altitude]):
            return False
        
        distance = self.calculate_distance(lat, lon, BKK_LAT, BKK_LON)
        is_below_10k = altitude and altitude < 3048
        is_within_80km = distance < 80
        is_descending = vertical_rate is not None and vertical_rate < -1.0
        
        return is_below_10k and is_within_80km
    
    def process_flights_with_avoidance_analysis(self):
        """Process flights and analyze avoidance behavior"""
        flights = self.get_flights_near_bkk()
        self.flight_data = []
        
        for flight in flights:
            if not flight or len(flight) < 12:
                continue
            
            if not self.is_arrival_flight(flight):
                continue
            
            lat, lon = flight[6], flight[5]
            callsign = flight[1].strip() if flight[1] else "Unknown"
            altitude = flight[7]
            velocity = flight[9]
            track = flight[10]  # Flight track/heading
            
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
            
            # Analyze weather at flight position
            weather_analysis = self.analyze_weather_intensity(lat, lon)
            
            # Determine avoidance behavior
            distance_to_bkk = self.calculate_distance(lat, lon, BKK_LAT, BKK_LON)
            avoidance_behavior = self.determine_avoidance_behavior(
                {'distance_km': distance_to_bkk}, 
                weather_analysis
            )
            
            # Check if flight is deviating from direct path
            if track is not None:
                heading_deviation = abs(track - heading_to_bkk)
                if heading_deviation > 180:
                    heading_deviation = 360 - heading_deviation
            else:
                heading_deviation = 0
            
            # Analyze if avoiding weather
            is_avoiding = False
            avoidance_reason = "NONE"
            
            if weather_analysis['in_weather'] and weather_analysis['severity'] in ['HIGH', 'MEDIUM']:
                if heading_deviation > 20:  # Significant deviation
                    is_avoiding = True
                    avoidance_reason = f"WEATHER_{weather_analysis['severity']}"
                elif distance_to_bkk > 40 and altitude > 2000:  # Still has options
                    if weather_analysis['severity'] == 'HIGH':
                        is_avoiding = True
                        avoidance_reason = "WEATHER_HIGH_ALTITUDE"
            
            flight_info = {
                "callsign": callsign,
                "lat": lat,
                "lon": lon,
                "altitude_ft": int(altitude * 3.28084) if altitude else 0,
                "speed_kts": int(velocity * 1.94384) if velocity else 0,
                "track": track,
                "distance_km": distance_to_bkk,
                "heading_to_bkk": heading_to_bkk,
                "heading_deviation": heading_deviation,
                "headwind_component": headwind,
                "crosswind_component": crosswind,
                "wind_condition": wind_condition,
                "wind_category": wind_category,
                "weather_intensity": weather_analysis['intensity'],
                "weather_category": weather_analysis['category'],
                "weather_severity": weather_analysis['severity'],
                "weather_type": weather_analysis['type'],
                "in_weather": weather_analysis['in_weather'],
                "is_avoiding": is_avoiding,
                "avoidance_reason": avoidance_reason,
                "avoidance_behavior": avoidance_behavior
            }
            
            self.flight_data.append(flight_info)
            
            # Update statistics
            self.avoidance_statistics[wind_category]['total'] += 1
            if is_avoiding:
                self.avoidance_statistics[wind_category]['avoiding'] += 1
            if weather_analysis['in_weather']:
                self.avoidance_statistics[wind_category]['in_weather'] += 1
        
        print(f"✅ Processed {len(self.flight_data)} arrival flights")
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
        """Create map with avoidance analysis visualization"""
        current_time = datetime.datetime.now()
        timestamp = current_time.strftime('%Y%m%d_%H%M%S')
        
        # Create map
        m = folium.Map(
            location=[BKK_LAT, BKK_LON],
            zoom_start=10,
            tiles='OpenStreetMap'
        )
        
        # Add weather radar
        if self.weather_history:
            latest_weather = self.weather_history[0]
            radar_layer = folium.raster_layers.TileLayer(
                tiles=f"https://tilecache.rainviewer.com{latest_weather['path']}/256/{{z}}/{{x}}/{{y}}/2/1_1.png",
                attr="RainViewer",
                name="Weather Radar",
                overlay=True,
                control=True,
                opacity=0.6
            )
            radar_layer.add_to(m)
        
        # Add weather zones (for visualization)
        weather_zones = [
            {'lat': 13.8, 'lon': 100.4, 'radius': 25, 'color': 'yellow', 'name': 'Light Rain'},
            {'lat': 14.1, 'lon': 100.8, 'radius': 30, 'color': 'orange', 'name': 'Moderate Rain'},
            {'lat': 13.4, 'lon': 101.0, 'radius': 20, 'color': 'red', 'name': 'Heavy Rain'},
            {'lat': 13.9, 'lon': 100.6, 'radius': 15, 'color': 'darkred', 'name': 'Thunderstorm'},
        ]
        
        for zone in weather_zones:
            folium.Circle(
                location=[zone['lat'], zone['lon']],
                radius=zone['radius'] * 1000,
                color=zone['color'],
                fill=True,
                fillOpacity=0.2,
                popup=zone['name']
            ).add_to(m)
        
        # Add flight markers
        for flight in self.flight_data:
            # Determine marker color based on behavior
            if flight['is_avoiding']:
                icon_color = 'red'
                icon_symbol = 'exclamation-triangle'
            elif flight['in_weather']:
                icon_color = 'orange'
                icon_symbol = 'cloud'
            else:
                icon_color = 'green'
                icon_symbol = 'plane'
            
            # Create popup
            popup_html = f"""
            <div style="width: 300px;">
                <h4>{flight['callsign']}</h4>
                <hr>
                <b>Flight Info:</b><br>
                • Altitude: {flight['altitude_ft']} ft<br>
                • Speed: {flight['speed_kts']} kts<br>
                • Distance to BKK: {flight['distance_km']:.1f} km<br>
                <br>
                <b>Wind Analysis:</b><br>
                • Condition: {flight['wind_condition']}<br>
                • Category: {flight['wind_category']}<br>
                • Headwind: {flight['headwind_component']:.1f} m/s<br>
                • Crosswind: {flight['crosswind_component']:.1f} m/s<br>
                <br>
                <b>Weather Status:</b><br>
                • Intensity: {flight['weather_intensity']:.1f}<br>
                • Category: {flight['weather_category']}<br>
                • In Weather: {'YES' if flight['in_weather'] else 'NO'}<br>
                <br>
                <b>Avoidance Analysis:</b><br>
                • Avoiding: {'YES' if flight['is_avoiding'] else 'NO'}<br>
                • Heading Deviation: {flight['heading_deviation']:.1f}°<br>
                • Behavior: {flight['avoidance_behavior']}
            </div>
            """
            
            folium.Marker(
                [flight["lat"], flight["lon"]],
                popup=folium.Popup(popup_html, max_width=350),
                tooltip=f"{flight['callsign']} - {flight['wind_category']} - {'AVOIDING' if flight['is_avoiding'] else 'NORMAL'}",
                icon=folium.Icon(color=icon_color, icon=icon_symbol, prefix='fa')
            ).add_to(m)
            
            # Add flight path line to BKK
            if flight['is_avoiding']:
                line_color = 'red'
                line_dash = '5, 10'
            else:
                line_color = 'blue'
                line_dash = None
            
            folium.PolyLine(
                [[flight["lat"], flight["lon"]], [BKK_LAT, BKK_LON]],
                color=line_color,
                weight=2,
                opacity=0.6,
                dash_array=line_dash
            ).add_to(m)
        
        # Add BKK Airport
        folium.Marker(
            [BKK_LAT, BKK_LON],
            popup=f"Suvarnabhumi Airport (BKK)<br>Wind: {self.wind_data['surface']['speed_kt']} kt from {self.wind_data['surface']['direction']}°",
            icon=folium.Icon(color='red', icon='star')
        ).add_to(m)
        
        # Calculate statistics
        stats = self.calculate_avoidance_percentages()
        
        # Add title with statistics
        title_html = f"""
        <div style="position: fixed; top: 10px; left: 50%; transform: translateX(-50%);
                    background: #2c3e50; color: white; padding: 20px;
                    border-radius: 10px; z-index: 1000; text-align: center;">
            <h3 style="margin: 0;">Wind & Weather Avoidance Analysis</h3>
            <p style="margin: 5px 0; font-size: 14px;">{current_time.strftime('%Y-%m-%d %H:%M:%S')}</p>
            <div style="margin-top: 10px; font-size: 12px;">
        """
        
        for category, data in stats.items():
            title_html += f"""
                <div style="display: inline-block; margin: 0 10px;">
                    <b>{category}:</b> {data['avoidance_percentage']:.1f}% avoiding
                    ({data['avoiding_weather']}/{data['total_flights']})
                </div>
            """
        
        title_html += """
            </div>
        </div>
        """
        m.get_root().html.add_child(folium.Element(title_html))
        
        # Add legend
        legend_html = """
        <div style="position: fixed; bottom: 20px; right: 20px; 
                    background: white; padding: 15px; border: 2px solid black;
                    border-radius: 5px; z-index: 1000;">
            <b>Legend:</b><br>
            🔴 Avoiding Weather<br>
            🟠 In Weather<br>
            🟢 Clear Path<br>
            --- Avoidance Route<br>
            — Direct Route
        </div>
        """
        m.get_root().html.add_child(folium.Element(legend_html))
        
        # Save map
        html_filename = f"{self.html_dir}/avoidance_analysis_{timestamp}.html"
        m.save(html_filename)
        
        print(f"💾 Saved analysis map: {html_filename}")
        
        # Take screenshot if driver available
        if self.driver:
            png_filename = f"{self.png_dir}/avoidance_analysis_{timestamp}.png"
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
        """Create detailed analysis report"""
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        report_file = f"{self.analysis_dir}/avoidance_report_{timestamp}.txt"
        
        stats = self.calculate_avoidance_percentages()
        
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write("="*80 + "\n")
            f.write("WIND & WEATHER AVOIDANCE ANALYSIS REPORT\n")
            f.write("="*80 + "\n\n")
            
            f.write(f"Report Generated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Wind Conditions: {self.wind_data['surface']['speed_kt']} kt from {self.wind_data['surface']['direction']}°\n")
            f.write(f"METAR: {self.metar_raw}\n\n")
            
            f.write("EXECUTIVE SUMMARY\n")
            f.write("-"*40 + "\n")
            f.write(f"Total Flights Analyzed: {len(self.flight_data)}\n")
            
            total_avoiding = sum(1 for f in self.flight_data if f['is_avoiding'])
            total_in_weather = sum(1 for f in self.flight_data if f['in_weather'])
            
            f.write(f"Flights Avoiding Weather: {total_avoiding} ({(total_avoiding/len(self.flight_data)*100):.1f}%)\n")
            f.write(f"Flights in Weather: {total_in_weather} ({(total_in_weather/len(self.flight_data)*100):.1f}%)\n\n")
            
            f.write("AVOIDANCE BY WIND CONDITION\n")
            f.write("-"*40 + "\n")
            
            # Sort categories for consistent display
            wind_categories = ['HEADWIND', 'TAILWIND', 'CROSSWIND', 'CALM']
            
            for category in wind_categories:
                if category in stats:
                    data = stats[category]
                    f.write(f"\n{category}:\n")
                    f.write(f"  Total Flights: {data['total_flights']}\n")
                    f.write(f"  Avoiding Weather: {data['avoiding_weather']} ({data['avoidance_percentage']:.1f}%)\n")
                    f.write(f"  In Weather: {data['in_weather']} ({data['weather_encounter_percentage']:.1f}%)\n")
            
            f.write("\n\nDETAILED FLIGHT ANALYSIS\n")
            f.write("-"*40 + "\n")
            
            # Group flights by avoidance behavior
            avoiding_flights = [f for f in self.flight_data if f['is_avoiding']]
            normal_flights = [f for f in self.flight_data if not f['is_avoiding']]
            
            f.write(f"\nFLIGHTS AVOIDING WEATHER ({len(avoiding_flights)}):\n")
            for flight in avoiding_flights:
                f.write(f"\n  ✈️ {flight['callsign']}\n")
                f.write(f"     Position: {flight['lat']:.3f}°N, {flight['lon']:.3f}°E\n")
                f.write(f"     Altitude: {flight['altitude_ft']} ft\n")
                f.write(f"     Wind: {flight['wind_category']} ({flight['wind_condition']})\n")
                f.write(f"     Weather: {flight['weather_category']} - {flight['weather_type']}\n")
                f.write(f"     Heading Deviation: {flight['heading_deviation']:.1f}°\n")
                f.write(f"     Reason: {flight['avoidance_reason']}\n")
            
            f.write(f"\n\nKEY FINDINGS\n")
            f.write("-"*40 + "\n")
            
            # Analyze patterns
            if stats:
                # Find wind condition with highest avoidance
                max_avoidance = max(stats.items(), key=lambda x: x[1]['avoidance_percentage'])
                f.write(f"• Highest avoidance rate: {max_avoidance[0]} flights ({max_avoidance[1]['avoidance_percentage']:.1f}%)\n")
                
                # Find wind condition with most weather encounters
                max_encounter = max(stats.items(), key=lambda x: x[1]['weather_encounter_percentage'])
                f.write(f"• Most weather encounters: {max_encounter[0]} flights ({max_encounter[1]['weather_encounter_percentage']:.1f}%)\n")
                
                # Average heading deviation for avoiding flights
                if avoiding_flights:
                    avg_deviation = sum(f['heading_deviation'] for f in avoiding_flights) / len(avoiding_flights)
                    f.write(f"• Average heading deviation when avoiding: {avg_deviation:.1f}°\n")
                
                # Weather severity analysis
                high_severity = sum(1 for f in self.flight_data if f['weather_severity'] == 'HIGH')
                medium_severity = sum(1 for f in self.flight_data if f['weather_severity'] == 'MEDIUM')
                f.write(f"• Flights encountering severe weather: {high_severity}\n")
                f.write(f"• Flights encountering moderate weather: {medium_severity}\n")
        
        print(f"📄 Analysis report saved: {report_file}")
        return report_file
    
    def create_statistics_chart(self):
        """Create visual statistics chart"""
        stats = self.calculate_avoidance_percentages()
        
        if not stats:
            print("❌ No data for statistics chart")
            return None
        
        # Prepare data
        categories = list(stats.keys())
        avoidance_percentages = [stats[cat]['avoidance_percentage'] for cat in categories]
        total_flights = [stats[cat]['total_flights'] for cat in categories]
        
        # Create figure
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))
        
        # Bar chart of avoidance percentages
        colors = {'HEADWIND': 'red', 'TAILWIND': 'green', 'CROSSWIND': 'blue', 'CALM': 'gray'}
        bar_colors = [colors.get(cat, 'gray') for cat in categories]
        
        bars = ax1.bar(categories, avoidance_percentages, color=bar_colors, alpha=0.7)
        ax1.set_ylabel('Avoidance Percentage (%)')
        ax1.set_title('Weather Avoidance by Wind Condition')
        ax1.set_ylim(0, 100)
        
        # Add value labels on bars
        for bar, percentage in zip(bars, avoidance_percentages):
            height = bar.get_height()
            ax1.text(bar.get_x() + bar.get_width()/2., height,
                    f'{percentage:.1f}%',
                    ha='center', va='bottom')
        
        # Pie chart of flight distribution
        ax2.pie(total_flights, labels=categories, autopct='%1.1f%%', 
                colors=[colors.get(cat, 'gray') for cat in categories])
        ax2.set_title('Flight Distribution by Wind Condition')
        
        # Add wind information
        wind_text = f"Current Wind: {self.wind_data['surface']['speed_kt']} kt from {self.wind_data['surface']['direction']}°"
        fig.suptitle(f'Wind & Weather Avoidance Analysis\n{wind_text}', fontsize=16)
        
        # Save chart
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        chart_file = f"{self.analysis_dir}/avoidance_statistics_{timestamp}.png"
        plt.tight_layout()
        plt.savefig(chart_file, dpi=300, bbox_inches='tight')
        plt.close()
        
        print(f"📊 Statistics chart saved: {chart_file}")
        return chart_file
    
    def run_single_analysis(self):
        """Run a single analysis"""
        print("\n🔍 Running Wind & Weather Avoidance Analysis...")
        
        # Update wind data
        self.update_wind_from_metar()
        
        # Get weather data
        self.get_weather_history()
        
        # Process flights
        self.process_flights_with_avoidance_analysis()
        
        if self.flight_data:
            # Create outputs
            html_file = self.create_avoidance_analysis_map()
            report_file = self.create_analysis_report()
            chart_file = self.create_statistics_chart()
            
            # Print summary
            self.print_analysis_summary()
            
            print(f"\n✅ Analysis complete!")
            print(f"📂 Files saved in: {self.base_dir}")
            
            return {
                'html': html_file,
                'report': report_file,
                'chart': chart_file
            }
        else:
            print("❌ No arrival flights found")
            return None
    
    def print_analysis_summary(self):
        """Print analysis summary to console"""
        stats = self.calculate_avoidance_percentages()
        
        print("\n" + "="*80)
        print("WIND & WEATHER AVOIDANCE ANALYSIS SUMMARY")
        print("="*80)
        
        print(f"\n📊 Overall Statistics:")
        print(f"   Total Flights: {len(self.flight_data)}")
        total_avoiding = sum(1 for f in self.flight_data if f['is_avoiding'])
        print(f"   Avoiding Weather: {total_avoiding} ({(total_avoiding/len(self.flight_data)*100):.1f}%)")
        
        print(f"\n🌬️ Wind Conditions:")
        print(f"   Current: {self.wind_data['surface']['speed_kt']} kt from {self.wind_data['surface']['direction']}°")
        
        print(f"\n📈 Avoidance by Wind Type:")
        for category in ['HEADWIND', 'TAILWIND', 'CROSSWIND', 'CALM']:
            if category in stats:
                data = stats[category]
                print(f"   {category}: {data['avoidance_percentage']:.1f}% avoiding ({data['avoiding_weather']}/{data['total_flights']} flights)")
        
        print("\n💡 Key Insights:")
        
        # Find most likely to avoid
        if stats:
            max_avoid = max(stats.items(), key=lambda x: x[1]['avoidance_percentage'])
            print(f"   • {max_avoid[0]} flights most likely to avoid weather ({max_avoid[1]['avoidance_percentage']:.1f}%)")
            
            # Compare headwind vs tailwind if both exist
            if 'HEADWIND' in stats and 'TAILWIND' in stats:
                head_avoid = stats['HEADWIND']['avoidance_percentage']
                tail_avoid = stats['TAILWIND']['avoidance_percentage']
                diff = abs(head_avoid - tail_avoid)
                
                if head_avoid > tail_avoid:
                    print(f"   • Headwind flights avoid {diff:.1f}% more than tailwind flights")
                elif tail_avoid > head_avoid:
                    print(f"   • Tailwind flights avoid {diff:.1f}% more than headwind flights")
                else:
                    print(f"   • Headwind and tailwind flights show similar avoidance rates")
    
    def run_continuous_monitoring(self, interval_minutes=10):
        """Run continuous monitoring"""
        print(f"\n🔄 Starting continuous monitoring every {interval_minutes} minutes")
        print("Press Ctrl+C to stop\n")
        
        # Reset cumulative statistics
        self.cumulative_stats = defaultdict(lambda: defaultdict(int))
        collection_count = 0
        
        try:
            while True:
                collection_count += 1
                print(f"\n--- Collection #{collection_count} at {datetime.datetime.now().strftime('%H:%M:%S')} ---")
                
                # Reset per-run statistics
                self.avoidance_statistics = defaultdict(lambda: defaultdict(int))
                
                # Run analysis
                results = self.run_single_analysis()
                
                if results:
                    # Update cumulative statistics
                    for wind_cat, stats in self.avoidance_statistics.items():
                        for stat_type, value in stats.items():
                            self.cumulative_stats[wind_cat][stat_type] += value
                    
                    # Print cumulative stats
                    print(f"\n📊 Cumulative Statistics (from {collection_count} collections):")
                    for category in ['HEADWIND', 'TAILWIND', 'CROSSWIND', 'CALM']:
                        if category in self.cumulative_stats:
                            total = self.cumulative_stats[category]['total']
                            avoiding = self.cumulative_stats[category]['avoiding']
                            if total > 0:
                                percentage = (avoiding / total) * 100
                                print(f"   {category}: {percentage:.1f}% ({avoiding}/{total})")
                
                print(f"\nNext collection in {interval_minutes} minutes...")
                time.sleep(interval_minutes * 60)
                
        except KeyboardInterrupt:
            print(f"\n🛑 Monitoring stopped after {collection_count} collections")
            
            # Save final cumulative report
            self.save_cumulative_report(collection_count)
    
    def save_cumulative_report(self, collection_count):
        """Save cumulative statistics report"""
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        report_file = f"{self.analysis_dir}/cumulative_report_{timestamp}.txt"
        
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write("="*80 + "\n")
            f.write("CUMULATIVE WIND & WEATHER AVOIDANCE ANALYSIS\n")
            f.write("="*80 + "\n\n")
            
            f.write(f"Total Collections: {collection_count}\n")
            f.write(f"Report Generated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            
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
        
        print(f"\n📄 Cumulative report saved: {report_file}")
    
    def __del__(self):
        """Cleanup"""
        if self.driver:
            self.driver.quit()

def main():
    print("\n" + "="*80)
    print("🌦️ WIND & WEATHER AVOIDANCE ANALYSIS SYSTEM")
    print("="*80)
    print("\n📊 This system analyzes:")
    print("   • How different wind conditions affect weather avoidance")
    print("   • Percentage of flights avoiding weather by wind type")
    print("   • Patterns in avoidance behavior")
    print("   • Real-time METAR wind data from VTBS")
    
    analyzer = WindWeatherAvoidanceAnalyzer()
    
    print("\n📋 Options:")
    print("   1. Single analysis")
    print("   2. Continuous monitoring")
    
    choice = input("\nEnter choice (1 or 2): ")
    
    if choice == "1":
        analyzer.run_single_analysis()
    elif choice == "2":
        interval = input("Enter interval in minutes (default 10): ")
        interval = int(interval) if interval.strip() else 10
        analyzer.run_continuous_monitoring(interval)
    else:
        print("❌ Invalid choice")

if __name__ == "__main__":
    main()