#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Time-Aware Weather Flight Radar
Addresses temporal mismatch between weather data and flight positions
"""

import matplotlib.pyplot as plt
import matplotlib.patches as patches
import numpy as np
import requests
import datetime
import json
from math import sin, cos, sqrt, atan2, radians
import time
import folium
import folium.plugins
import os
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# BKK Airport coordinates
BKK_LAT, BKK_LON = 13.6811, 100.7475
BANGKOK_CENTER_LAT, BANGKOK_CENTER_LON = 13.7563, 100.5018

# Bangkok metropolitan area bounds
BANGKOK_BOUNDS = {
    'north': 14.2, 'south': 13.2, 'east': 101.2, 'west': 100.0
}

# Flight tracking bounds
BBOX = {
    "lamin": 13.1, "lamax": 14.3, "lomin": 100.2, "lomax": 101.3
}

class TimeAwareWeatherFlightRadar:
    def __init__(self, thailand_map_path=None):
        self.thailand_map_path = thailand_map_path
        self.thailand_segments = []
        self.flight_data = []
        self.weather_history = []  # Store multiple weather frames
        self.driver = None
        self.setup_driver()
        
    def setup_driver(self):
        """Setup Chrome driver for screenshot capture"""
        try:
            chrome_options = Options()
            chrome_options.add_argument('--headless')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--window-size=1920,1080')
            chrome_options.add_argument('--disable-gpu')
            
            self.driver = webdriver.Chrome(options=chrome_options)
            print("✅ Chrome driver initialized successfully")
        except Exception as e:
            print(f"❌ Error setting up Chrome driver: {str(e)}")
            self.driver = None

    def get_weather_history(self, hours_back=2):
        """Get multiple weather radar frames for temporal analysis"""
        print("🌦️ Fetching weather radar history for temporal analysis...")
        
        try:
            url = "https://api.rainviewer.com/public/weather-maps.json"
            response = requests.get(url, timeout=30)
            data = response.json()
            
            # Get all past radar frames
            all_frames = data.get("radar", {}).get("past", [])
            
            if not all_frames:
                print("❌ No radar history available")
                return []
            
            # Get frames from past 2 hours
            now = datetime.datetime.now()
            cutoff_time = int((now - datetime.timedelta(hours=hours_back)).timestamp())
            
            recent_frames = [frame for frame in all_frames if frame['time'] >= cutoff_time]
            
            # Convert to readable format
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
            
            # Sort by timestamp (newest first)
            weather_history.sort(key=lambda x: x['timestamp'], reverse=True)
            
            self.weather_history = weather_history
            print(f"✅ Got {len(weather_history)} weather frames from past {hours_back} hours")
            
            # Print frame ages for transparency
            for i, frame in enumerate(weather_history[:5]):  # Show first 5
                print(f"   Frame {i+1}: {frame['time_str']} ({frame['age_minutes']:.1f} min ago)")
            
            return weather_history
            
        except Exception as e:
            print(f"❌ Error fetching weather history: {str(e)}")
            return []

    def get_flights_near_bkk(self):
        """Fetch flights with timestamp information"""
        url = "https://opensky-network.org/api/states/all"
        try:
            flight_fetch_time = datetime.datetime.now()
            response = requests.get(url, params=BBOX, timeout=30)
            if response.status_code == 200:
                data = response.json()
                flights = data.get("states", [])
                print(f"✈️ Found {len(flights)} flights at {flight_fetch_time.strftime('%H:%M:%S')}")
                return flights, flight_fetch_time
            else:
                print(f"❌ Failed to fetch flight data: {response.status_code}")
                return [], None
        except Exception as e:
            print(f"❌ Error fetching flight data: {str(e)}")
            return [], None

    def calculate_distance(self, lat1, lon1, lat2, lon2):
        """Calculate distance between two points in kilometers"""
        R = 6371.0
        lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
        dlon = lon2 - lon1
        dlat = lat2 - lat1
        a = sin(dlat/2)**2 + cos(lat1)*cos(lat2)*sin(dlon/2)**2
        c = 2 * atan2(sqrt(a), sqrt(1-a))
        return R * c

    def get_best_weather_frame_for_flight(self, flight_lat, flight_lon, flight_fetch_time):
        """
        Get the most appropriate weather frame for a flight position
        Considers flight movement and weather data age
        """
        if not self.weather_history:
            return None
        
        # For arriving flights, estimate when they were at current position
        # Assumption: flights move ~400-500 km/h, so in 5 minutes they move ~30-40km
        
        best_frame = None
        min_time_diff = float('inf')
        
        for frame in self.weather_history:
            frame_time = frame['datetime']
            time_diff_minutes = abs((flight_fetch_time - frame_time).total_seconds() / 60)
            
            # Prefer newer weather data (within 10 minutes is good)
            if time_diff_minutes < min_time_diff and time_diff_minutes <= 15:
                min_time_diff = time_diff_minutes
                best_frame = frame
        
        return best_frame, min_time_diff

    def analyze_weather_with_temporal_context(self, lat, lon, flight_fetch_time):
        """
        Analyze weather with temporal awareness
        """
        if not self.weather_history:
            return {
                'intensity': 0,
                'category': 'NO_DATA',
                'color': 'gray',
                'description': 'No weather data available',
                'data_age_minutes': None,
                'temporal_status': 'NO_DATA'
            }
        
        # Get best weather frame for this flight
        best_frame, time_diff = self.get_best_weather_frame_for_flight(lat, lon, flight_fetch_time)
        
        if not best_frame:
            return {
                'intensity': 0,
                'category': 'STALE_DATA',
                'color': 'gray',
                'description': 'Weather data too old',
                'data_age_minutes': None,
                'temporal_status': 'STALE'
            }
        
        # Determine temporal status
        if time_diff <= 5:
            temporal_status = 'CURRENT'
            confidence = 'HIGH'
        elif time_diff <= 10:
            temporal_status = 'RECENT'
            confidence = 'MEDIUM'
        elif time_diff <= 15:
            temporal_status = 'HISTORICAL'
            confidence = 'LOW'
        else:
            temporal_status = 'STALE'
            confidence = 'VERY_LOW'
        
        # Simplified weather intensity estimation
        # In reality, you'd query the actual radar tile data
        weather_zones = [
            {'lat': 13.8, 'lon': 100.4, 'radius': 25, 'intensity': 20, 'type': 'Light Rain'},
            {'lat': 14.1, 'lon': 100.8, 'radius': 30, 'intensity': 35, 'type': 'Moderate Rain'},
            {'lat': 13.4, 'lon': 101.0, 'radius': 20, 'intensity': 45, 'type': 'Heavy Rain'},
        ]
        
        max_intensity = 0
        weather_type = 'CLEAR'
        
        for zone in weather_zones:
            distance = self.calculate_distance(lat, lon, zone['lat'], zone['lon'])
            if distance <= zone['radius']:
                intensity_factor = max(0, 1 - (distance / zone['radius']))
                current_intensity = zone['intensity'] * intensity_factor
                
                # Reduce intensity for older data (weather moves/dissipates)
                age_factor = max(0.1, 1 - (time_diff / 20))  # Reduce intensity as data gets older
                current_intensity *= age_factor
                
                if current_intensity > max_intensity:
                    max_intensity = current_intensity
                    weather_type = zone['type']
        
        # Classify weather intensity
        if max_intensity >= 40:
            category = 'HEAVY'
            color = 'red'
        elif max_intensity >= 20:
            category = 'MODERATE'
            color = 'orange'
        elif max_intensity >= 5:
            category = 'LIGHT'
            color = 'yellow'
        else:
            category = 'CLEAR'
            color = 'green'
        
        return {
            'intensity': max_intensity,
            'category': category,
            'color': color,
            'description': weather_type,
            'data_age_minutes': time_diff,
            'temporal_status': temporal_status,
            'confidence': confidence,
            'weather_frame_time': best_frame['time_str']
        }

    def is_arrival_flight(self, flight):
        """Check if flight is arriving to BKK"""
        lat, lon, altitude = flight[6], flight[5], flight[7]
        vertical_rate = flight[11]
        
        if not all([lat, lon, altitude]):
            return False
        
        distance = self.calculate_distance(lat, lon, BKK_LAT, BKK_LON)
        is_below_arrival_alt = altitude < 3048  # Below 10,000 feet
        is_close_to_airport = distance < 80     # Within 80km
        is_descending = vertical_rate is not None and vertical_rate < -1.0
        is_final_approach = altitude < 1524 and distance < 30
        
        return is_below_arrival_alt and is_close_to_airport and (is_descending or is_final_approach)

    def process_flight_data_with_temporal_awareness(self, flight_fetch_time):
        """Process flight data with temporal weather analysis"""
        flights, _ = self.get_flights_near_bkk()
        if not flights:
            return []

        flight_classifications = []
        
        for flight in flights:
            if not flight or len(flight) < 12:
                continue
                
            if not self.is_arrival_flight(flight):
                continue
                
            lat, lon = flight[6], flight[5]
            callsign = flight[1].strip() if flight[1] else "Unknown"
            altitude = flight[7]
            velocity = flight[9]
            
            # Temporal weather analysis
            weather_analysis = self.analyze_weather_with_temporal_context(lat, lon, flight_fetch_time)
            
            # Determine flight action based on weather and data quality
            if weather_analysis['temporal_status'] == 'NO_DATA':
                action = "NO WEATHER DATA"
                classification = "UNKNOWN_CONDITIONS"
                risk_level = "UNKNOWN"
            elif weather_analysis['temporal_status'] == 'STALE':
                action = "WEATHER DATA TOO OLD"
                classification = "OUTDATED_ANALYSIS"
                risk_level = "UNCERTAIN"
            elif weather_analysis['intensity'] >= 40:
                action = f"WEATHER AVOIDANCE RECOMMENDED (Data: {weather_analysis['data_age_minutes']:.1f}min old)"
                classification = "HIGH_RISK_WEATHER"
                risk_level = "HIGH"
            elif weather_analysis['intensity'] >= 20:
                action = f"PROCEED WITH CAUTION (Data: {weather_analysis['data_age_minutes']:.1f}min old)"
                classification = "MODERATE_WEATHER"
                risk_level = "MODERATE"
            elif weather_analysis['intensity'] >= 5:
                action = f"LIGHT WEATHER DETECTED (Data: {weather_analysis['data_age_minutes']:.1f}min old)"
                classification = "LIGHT_WEATHER"
                risk_level = "LOW"
            else:
                action = f"CLEAR CONDITIONS (Data: {weather_analysis['data_age_minutes']:.1f}min old)"
                classification = "CLEAR_WEATHER"
                risk_level = "NONE"

            distance_to_bkk = self.calculate_distance(lat, lon, BKK_LAT, BKK_LON)
            
            flight_info = {
                "callsign": callsign,
                "lat": lat,
                "lon": lon,
                "altitude_ft": int(altitude * 3.28084) if altitude else None,
                "speed_kts": int(velocity * 1.94384) if velocity else None,
                "distance_km": distance_to_bkk,
                "weather_intensity": weather_analysis['intensity'],
                "weather_category": weather_analysis['category'],
                "weather_color": weather_analysis['color'],
                "weather_description": weather_analysis['description'],
                "data_age_minutes": weather_analysis['data_age_minutes'],
                "temporal_status": weather_analysis['temporal_status'],
                "confidence": weather_analysis['confidence'],
                "weather_frame_time": weather_analysis.get('weather_frame_time', 'N/A'),
                "action": action,
                "classification": classification,
                "risk_level": risk_level
            }
            
            flight_classifications.append(flight_info)

        self.flight_data = flight_classifications
        return flight_classifications

    def create_temporal_aware_map(self, save_html=True, save_images=True):
        """Create map with temporal awareness indicators"""
        current_time = datetime.datetime.now()
        formatted_time = current_time.strftime("%Y-%m-%d %H:%M:%S")
        
        # Create base folder
        base_folder = "temporal_weather_flight_data"
        if not os.path.exists(base_folder):
            os.makedirs(base_folder)
        
        date_folder = os.path.join(base_folder, current_time.strftime("%Y%m%d"))
        if not os.path.exists(date_folder):
            os.makedirs(date_folder)
        
        time_str = current_time.strftime('%H%M%S')
        html_file = os.path.join(date_folder, f"temporal_weather_flight_{time_str}.html")
        png_file = os.path.join(date_folder, f"temporal_weather_flight_{time_str}.png")
        summary_file = os.path.join(date_folder, f"temporal_weather_flight_{time_str}_data.txt")
        
        try:
            # Create map
            m = folium.Map(
                location=[BANGKOK_CENTER_LAT, BANGKOK_CENTER_LON], 
                zoom_start=10,
                tiles='OpenStreetMap',
                width='100%',
                height='100%'
            )
            
            # Add latest weather radar overlay
            if self.weather_history:
                latest_weather = self.weather_history[0]
                print(f"🌦️ Adding weather overlay from: {latest_weather['time_str']} ({latest_weather['age_minutes']:.1f} min ago)")
                
                radar_layer = folium.raster_layers.TileLayer(
                    tiles=f"https://tilecache.rainviewer.com{latest_weather['path']}/256/{{z}}/{{x}}/{{y}}/2/1_1.png",
                    attr="RainViewer | Time-Aware Weather Data",
                    name="Weather Radar (Latest)",
                    overlay=True,
                    control=True,
                    opacity=0.7
                )
                radar_layer.add_to(m)
                weather_status = f"Weather: {latest_weather['time_str']} ({latest_weather['age_minutes']:.1f}min ago)"
            else:
                weather_status = "No Weather Data Available"
            
            # Flight colors based on temporal confidence
            confidence_colors = {
                "HIGH": "green",      # Data is very recent
                "MEDIUM": "yellow",   # Data is somewhat recent
                "LOW": "orange",      # Data is old but usable
                "VERY_LOW": "red",    # Data is very old
                "UNKNOWN": "gray"     # No data
            }
            
            # Add flight positions with temporal awareness
            for flight in self.flight_data:
                base_color = confidence_colors.get(flight.get("confidence", "UNKNOWN"), "gray")
                
                # Create detailed popup with temporal info
                popup_html = f"""
                <div style="width: 300px;">
                    <h4><b>{flight['callsign']}</b></h4>
                    <hr>
                    <b>Flight Info:</b><br>
                    • Altitude: {flight['altitude_ft']} ft<br>
                    • Speed: {flight['speed_kts']} kts<br>
                    • Distance to BKK: {flight['distance_km']:.1f} km<br>
                    <br>
                    <b>Weather Analysis:</b><br>
                    • Intensity: {flight['weather_intensity']:.1f} dBZ<br>
                    • Category: {flight['weather_category']}<br>
                    • Conditions: {flight['weather_description']}<br>
                    <br>
                    <b>⏰ Temporal Analysis:</b><br>
                    • Weather Data Age: {flight['data_age_minutes']:.1f} minutes<br>
                    • Data Status: {flight['temporal_status']}<br>
                    • Confidence: {flight['confidence']}<br>
                    • Weather Frame: {flight['weather_frame_time']}<br>
                    <br>
                    <b>Assessment:</b><br>
                    {flight['action']}
                </div>
                """
                
                # Create custom icon based on temporal confidence
                if flight.get("confidence") == "HIGH":
                    icon_color = "green"
                    icon_symbol = "plane"
                elif flight.get("confidence") == "MEDIUM":
                    icon_color = "orange"
                    icon_symbol = "plane"
                elif flight.get("confidence") == "LOW":
                    icon_color = "red"
                    icon_symbol = "question"
                else:
                    icon_color = "gray"
                    icon_symbol = "question"
                
                folium.Marker(
                    [flight["lat"], flight["lon"]],
                    popup=folium.Popup(popup_html, max_width=350),
                    tooltip=f"{flight['callsign']} - Data: {flight['data_age_minutes']:.1f}min old",
                    icon=folium.Icon(color=icon_color, icon=icon_symbol, prefix='fa')
                ).add_to(m)
            
            # Add airports
            folium.Marker(
                [BKK_LAT, BKK_LON], 
                tooltip="BKK Airport",
                popup="Suvarnabhumi Airport (BKK)",
                icon=folium.Icon(color='red', icon='plane', prefix='fa')
            ).add_to(m)
            
            # Set map bounds
            m.fit_bounds([
                [BANGKOK_BOUNDS['south'], BANGKOK_BOUNDS['west']],
                [BANGKOK_BOUNDS['north'], BANGKOK_BOUNDS['east']]
            ])
            
            # Calculate statistics
            total_flights = len(self.flight_data)
            high_conf = sum(1 for f in self.flight_data if f.get("confidence") == "HIGH")
            medium_conf = sum(1 for f in self.flight_data if f.get("confidence") == "MEDIUM")
            low_conf = sum(1 for f in self.flight_data if f.get("confidence") == "LOW")
            
            # Enhanced title with temporal awareness
            title_html = f'''
                <div style="position: fixed; 
                            top: 15px; 
                            left: 50%; 
                            transform: translateX(-50%);
                            width: 650px; 
                            height: 140px; 
                            z-index:9999; 
                            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                            color: white;
                            font-family: Arial, sans-serif;
                            font-size: 16px;
                            font-weight: bold;
                            padding: 15px;
                            border-radius: 15px;
                            border: 3px solid #fff;
                            text-align: center;
                            box-shadow: 0 4px 15px rgba(0,0,0,0.3);">
                    ⏰ Bangkok Time-Aware Weather Flight Radar<br>
                    <span style="font-size: 14px; font-weight: normal;">📅 Flight Data: {formatted_time}</span><br>
                    <span style="font-size: 12px; font-weight: normal;">🌦️ {weather_status}</span><br>
                    <span style="font-size: 11px; font-weight: normal;">
                        Total: {total_flights} | High Conf: {high_conf} | Medium: {medium_conf} | Low: {low_conf}
                    </span><br>
                    <span style="font-size: 10px; font-weight: normal; color: #ffeb3b;">
                        ⚠️ Analysis considers weather data age & flight movement
                    </span><br>
                    <span style="font-size: 9px; font-weight: normal; color: #e8f5e8;">
                        🟢 = Recent Data | 🟡 = Older Data | 🔴 = Stale Data
                    </span>
                </div>
            '''
            m.get_root().html.add_child(folium.Element(title_html))
            
            # Save files
            if save_html:
                m.save(html_file)
                print(f"💾 Saved HTML: {os.path.basename(html_file)}")
            
            if save_images and self.driver:
                self.capture_screenshot_png(html_file, png_file, formatted_time)
            
            # Create detailed summary
            with open(summary_file, 'w', encoding='utf-8') as f:
                f.write(f"⏰ TIME-AWARE WEATHER FLIGHT RADAR DATA\n")
                f.write(f"=" * 60 + "\n\n")
                f.write(f"📅 Flight Collection Time: {formatted_time}\n")
                
                if self.weather_history:
                    f.write(f"🌦️ Latest Weather Frame: {self.weather_history[0]['time_str']}\n")
                    f.write(f"⏱️ Weather Data Age: {self.weather_history[0]['age_minutes']:.1f} minutes\n")
                    f.write(f"📊 Weather Frames Available: {len(self.weather_history)}\n")
                else:
                    f.write(f"🌦️ Weather Data: NOT AVAILABLE\n")
                
                f.write(f"\n⚠️ TEMPORAL ANALYSIS EXPLANATION:\n")
                f.write(f"Weather radar data is collected every ~5-10 minutes.\n")
                f.write(f"Flights move ~30-40km in 5 minutes at approach speeds.\n")
                f.write(f"Weather patterns can shift/dissipate quickly.\n")
                f.write(f"Analysis considers data age and flight movement.\n\n")
                
                f.write(f"DATA CONFIDENCE LEVELS:\n")
                f.write(f"🟢 HIGH: Weather data <5min old (very reliable)\n")
                f.write(f"🟡 MEDIUM: Weather data 5-10min old (fairly reliable)\n")
                f.write(f"🟠 LOW: Weather data 10-15min old (less reliable)\n")
                f.write(f"🔴 VERY_LOW: Weather data >15min old (unreliable)\n\n")
                
                f.write(f"FLIGHT ANALYSIS:\n")
                for i, flight in enumerate(self.flight_data, 1):
                    conf_icon = {"HIGH": "🟢", "MEDIUM": "🟡", "LOW": "🟠", "VERY_LOW": "🔴", "UNKNOWN": "⚪"}
                    icon = conf_icon.get(flight.get("confidence", "UNKNOWN"), "❓")
                    
                    f.write(f"{i}. {icon} {flight['callsign']} | {flight['weather_category']} Weather\n")
                    f.write(f"   📍 {flight['lat']:.3f}°N, {flight['lon']:.3f}°E | {flight['altitude_ft']}ft\n")
                    f.write(f"   ⏰ Weather Data Age: {flight['data_age_minutes']:.1f} minutes\n")
                    f.write(f"   🎯 Confidence: {flight['confidence']} | Status: {flight['temporal_status']}\n")
                    f.write(f"   🌦️ Analysis: {flight['weather_description']} ({flight['weather_intensity']:.1f} dBZ)\n")
                    f.write(f"   📋 Action: {flight['action']}\n\n")
            
            print(f"✅ Temporal-aware flight data saved: {formatted_time}")
            return html_file
            
        except Exception as e:
            print(f"❌ Error creating temporal-aware map: {str(e)}")
            return None

    def capture_screenshot_png(self, html_file, png_file, formatted_time):
        """Capture PNG screenshot"""
        try:
            file_url = f"file://{os.path.abspath(html_file)}"
            self.driver.get(file_url)
            
            print(f"📸 Taking temporal-aware screenshot for {formatted_time}...")
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CLASS_NAME, "leaflet-container"))
            )
            
            time.sleep(5)
            
            self.driver.set_window_size(1920, 1080)
            self.driver.save_screenshot(png_file)
            print(f"🖼️ Saved temporal-aware PNG: {os.path.basename(png_file)}")
                
        except Exception as e:
            print(f"❌ Error capturing screenshot: {str(e)}")

    def run_temporal_aware_monitoring(self, interval_minutes=10):
        """Run monitoring with temporal awareness"""
        print(f"⏰ Starting TIME-AWARE weather flight monitoring every {interval_minutes} minutes.")
        print(f"🌦️ Considers weather data age and flight movement timing")
        print(f"📊 Shows confidence levels based on data freshness")
        print(f"🛑 Press Ctrl+C to stop.")
        
        collection_count = 0
        
        try:
            while True:
                current_time = datetime.datetime.now()
                formatted_time = current_time.strftime("%Y-%m-%d %H:%M:%S")
                collection_count += 1
                
                print(f"\n🕐 [{formatted_time}] Temporal-aware collection #{collection_count}")
                print("-" * 70)
                
                # Get weather history for temporal analysis
                weather_history = self.get_weather_history()
                
                # Process flight data with temporal awareness
                flights = self.process_flight_data_with_temporal_awareness(current_time)
                
                if flights or weather_history:
                    html_file = self.create_temporal_aware_map()
                    if html_file:
                        print(f"✅ Temporal-aware collection #{collection_count} successful")
                        self.print_temporal_summary()
                    else:
                        print(f"❌ Temporal-aware collection #{collection_count} failed")
                else:
                    print("📊 No data available")
                
                next_time = current_time + datetime.timedelta(minutes=interval_minutes)
                print(f"⏰ Next temporal-aware collection at: {next_time.strftime('%H:%M:%S')}")
                
                time.sleep(interval_minutes * 60)
                
        except KeyboardInterrupt:
            print(f"\n🛑 Temporal-aware monitoring stopped after {collection_count} collections")
        finally:
            if self.driver:
                self.driver.quit()

    def print_temporal_summary(self):
        """Print summary with temporal awareness"""
        if not self.flight_data:
            print("📊 No flight data to summarize")
            return
        
        print("\n" + "="*80)
        print("⏰ TEMPORAL-AWARE WEATHER FLIGHT ANALYSIS")
        print("="*80)
        
        # Weather status
        if self.weather_history:
            latest = self.weather_history[0]
            print(f"🌦️ Latest Weather Data: {latest['time_str']} ({latest['age_minutes']:.1f} min ago)")
            print(f"📊 Weather Frames Available: {len(self.weather_history)}")
        else:
            print("🌦️ Weather Data: NOT AVAILABLE")
        
        print(f"⚠️ IMPORTANT: Analysis considers weather data age vs flight positions")
        print(f"   • Weather moves/changes over time")
        print(f"   • Flights move ~30-40km in 5 minutes")
        print(f"   • Older weather data = lower confidence")
        
        # Group flights by confidence level
        confidence_groups = {}
        for flight in self.flight_data:
            conf = flight.get('confidence', 'UNKNOWN')
            if conf not in confidence_groups:
                confidence_groups[conf] = []
            confidence_groups[conf].append(flight)
        
        # Print by confidence level
        conf_order = ['HIGH', 'MEDIUM', 'LOW', 'VERY_LOW', 'UNKNOWN']
        conf_icons = {'HIGH': '🟢', 'MEDIUM': '🟡', 'LOW': '🟠', 'VERY_LOW': '🔴', 'UNKNOWN': '⚪'}
        
        for conf in conf_order:
            if conf in confidence_groups:
                flights = confidence_groups[conf]
                icon = conf_icons[conf]
                print(f"\n{icon} {conf} CONFIDENCE ({len(flights)} flights):")
                
                for flight in flights:
                    print(f"   ✈️ {flight['callsign']} | {flight['weather_category']} Weather")
                    print(f"      📍 {flight['lat']:.3f}°N, {flight['lon']:.3f}°E | {flight['altitude_ft']}ft")
                    print(f"      ⏰ Weather Data: {flight['data_age_minutes']:.1f} min old | Status: {flight['temporal_status']}")
                    print(f"      🌦️ Conditions: {flight['weather_description']} ({flight['weather_intensity']:.1f} dBZ)")
                    print(f"      📋 Action: {flight['action']}")

    def create_single_temporal_analysis(self):
        """Create single temporal-aware analysis"""
        print("⏰ Creating single temporal-aware flight weather analysis...")
        
        current_time = datetime.datetime.now()
        
        # Get weather history
        weather_history = self.get_weather_history()
        
        # Process flights with temporal awareness
        flights = self.process_flight_data_with_temporal_awareness(current_time)
        
        if flights or weather_history:
            html_file = self.create_temporal_aware_map()
            if html_file:
                self.print_temporal_summary()
                print(f"\n📂 Open this file in your browser: {html_file}")
                print("\n⏰ TEMPORAL ANALYSIS EXPLANATION:")
                print("   • Green markers: Recent weather data (high confidence)")
                print("   • Yellow markers: Somewhat old data (medium confidence)")
                print("   • Orange markers: Old data (low confidence)")
                print("   • Red markers: Very old data (very low confidence)")
                print("   • Gray markers: No weather data available")
                print("\n🌦️ Weather radar shows the most recent available frame")
                print("   • Click on flight markers to see detailed temporal analysis")
                print("   • Data age and confidence levels are clearly indicated")
                return html_file
            else:
                print("❌ Failed to create temporal analysis")
                return None
        else:
            print("❌ No data available for analysis")
            return None

    def __del__(self):
        """Cleanup"""
        if self.driver:
            self.driver.quit()

def main():
    print("\n" + "="*80)
    print("⏰ TIME-AWARE WEATHER FLIGHT RADAR")
    print("="*80)
    print("🎯 SOLVES THE TEMPORAL MISMATCH PROBLEM:")
    print("   ❌ Old Issue: 5-minute old weather data analyzed with current flights")
    print("   ✅ New Approach: Considers weather data age and flight movement")
    print("   📊 Shows confidence levels based on data freshness")
    print("   ⏰ Honest about when weather analysis is unreliable")
    print("\n✨ Features:")
    print("   🌦️ Multi-frame weather history analysis")
    print("   📈 Temporal confidence scoring")
    print("   🎯 Flight-specific weather data matching")
    print("   📋 Honest uncertainty reporting")
    print("   🔍 Visual confidence indicators")
    
    radar = TimeAwareWeatherFlightRadar()
    
    if not radar.driver:
        print("\n⚠️ WARNING: Screenshot capture disabled (Chrome driver not available)")
        proceed = input("   Continue with HTML only? (y/n): ")
        if proceed.lower() != 'y':
            return
    
    print("\n📋 Options:")
    print("   1. Single temporal-aware analysis")
    print("   2. Continuous temporal-aware monitoring")
    
    choice = input("\n🎯 Enter your choice (1 or 2): ")
    
    if choice == "1":
        html_file = radar.create_single_temporal_analysis()
        
    elif choice == "2":
        try:
            interval = input("⏱️ Enter monitoring interval in minutes (default: 10): ")
            interval = int(interval) if interval.strip() else 10
            if interval < 5:
                print("⚠️ Minimum interval is 5 minutes.")
                interval = 5
            radar.run_temporal_aware_monitoring(interval)
        except ValueError:
            print("❌ Invalid input. Using default (10 minutes).")
            radar.run_temporal_aware_monitoring(10)
    
    else:
        print("❌ Invalid choice.")

if __name__ == "__main__":
    main()