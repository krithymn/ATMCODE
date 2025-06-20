#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Enhanced Bangkok Flight Weather Radar with Interactive Map Integration
Combines real-time flight tracking with detailed interactive maps like the weather radar system
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

# Bangkok metropolitan area bounds (same as weather radar)
BANGKOK_BOUNDS = {
    'north': 14.2,   # North of Bangkok
    'south': 13.2,   # South of Bangkok  
    'east': 101.2,   # East of Bangkok
    'west': 100.0    # West of Bangkok
}

# Flight tracking bounds (focused on Bangkok area)
BBOX = {
    "lamin": 13.1,   # South
    "lamax": 14.3,   # North  
    "lomin": 100.2,  # West
    "lomax": 101.3   # East
}

# Weather echo classifications
ECHO_CLASSIFICATIONS = {
    "GREEN": {"min_dbz": 5, "max_dbz": 30, "color": "green", "alpha": 0.3},
    "YELLOW": {"min_dbz": 30, "max_dbz": 40, "color": "yellow", "alpha": 0.4},
    "ORANGE": {"min_dbz": 40, "max_dbz": 50, "color": "orange", "alpha": 0.5},
    "RED": {"min_dbz": 50, "max_dbz": 60, "color": "red", "alpha": 0.6},
    "MAGENTA": {"min_dbz": 60, "max_dbz": 100, "color": "magenta", "alpha": 0.7}
}

class EnhancedBangkokFlightRadar:
    def __init__(self, thailand_map_path=None):
        self.thailand_map_path = thailand_map_path
        self.thailand_segments = []
        self.flight_data = []
        self.weather_zones = []
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
        
    def load_thailand_map(self):
        """Load Thailand outline from CSV file or create simplified version"""
        print("📍 Loading Thailand map outline...")
        
        if not self.thailand_map_path or not os.path.exists(self.thailand_map_path):
            print("📝 Creating simplified Thailand outline...")
            return self.create_simplified_thailand_outline()
        
        all_lon = []
        all_lat = []

        try:
            with open(self.thailand_map_path, "r", encoding="utf-8_sig") as frMAP:
                for i in range(0, 13538):
                    try:
                        readcell = frMAP.readline()
                        if not readcell:
                            break
                            
                        lonlat = readcell.split(",")
                        if len(lonlat) >= 2:
                            lon_tmp = float(lonlat[0])
                            lat_tmp = float(lonlat[1])
                            # Filter coordinates within Thailand bounds
                            if 95 <= lon_tmp <= 110 and 5 <= lat_tmp <= 25:
                                all_lon.append(lon_tmp)
                                all_lat.append(lat_tmp)
                    except (ValueError, IndexError):
                        continue
        except FileNotFoundError:
            print(f"❌ Thailand map file not found: {self.thailand_map_path}")
            return self.create_simplified_thailand_outline()

        print(f"✅ Loaded {len(all_lon)} valid coordinates")

        # Detect jumps and split into segments
        segments = []
        if all_lon:
            current_lon = [all_lon[0]]
            current_lat = [all_lat[0]]
            jump_threshold = 0.5

            for i in range(1, len(all_lon)):
                lon_diff = abs(all_lon[i] - all_lon[i-1])
                lat_diff = abs(all_lat[i] - all_lat[i-1])
                
                if lon_diff > jump_threshold or lat_diff > jump_threshold:
                    if len(current_lon) > 10:
                        segments.append((current_lon, current_lat))
                    current_lon = [all_lon[i]]
                    current_lat = [all_lat[i]]
                else:
                    current_lon.append(all_lon[i])
                    current_lat.append(all_lat[i])

            if len(current_lon) > 10:
                segments.append((current_lon, current_lat))

        self.thailand_segments = segments
        print(f"📊 Created {len(segments)} map segments")
        return True

    def create_simplified_thailand_outline(self):
        """Create simplified Thailand outline if map file is not available"""
        # More detailed Thailand border coordinates
        thailand_outline = [
            # Main Thailand outline (more detailed)
            ([97.5, 98.0, 98.5, 99.0, 99.5, 100.0, 100.5, 101.0, 101.5, 102.0, 102.5, 103.0, 103.5, 104.0, 104.5, 105.0, 
              104.8, 104.5, 104.0, 103.5, 103.0, 102.5, 102.0, 101.5, 101.0, 100.5, 100.0, 99.5, 99.0, 98.5, 98.0, 97.5, 97.5],
             [20.0, 19.8, 19.5, 19.2, 19.0, 18.8, 18.5, 18.0, 17.5, 16.5, 16.0, 15.0, 14.5, 13.5, 13.0, 12.0, 
              11.5, 11.0, 10.5, 10.0, 9.5, 9.0, 8.5, 8.0, 7.5, 8.0, 8.5, 9.5, 12.0, 15.0, 17.0, 18.5, 20.0]),
            # Bangkok area detail
            ([100.0, 100.2, 100.4, 100.6, 100.8, 101.0, 101.2, 101.2, 101.0, 100.8, 100.6, 100.4, 100.2, 100.0, 100.0],
             [13.2, 13.2, 13.1, 13.3, 13.5, 13.7, 13.9, 14.2, 14.3, 14.2, 14.0, 13.8, 13.5, 13.3, 13.2])
        ]
        
        self.thailand_segments = thailand_outline
        print("✅ Using simplified Thailand outline")
        return True

    def get_flights_near_bkk(self):
        """Fetch flights within BKK area using OpenSky API"""
        url = "https://opensky-network.org/api/states/all"
        try:
            response = requests.get(url, params=BBOX, timeout=30)
            if response.status_code == 200:
                data = response.json()
                flights = data.get("states", [])
                print(f"✈️ Found {len(flights)} flights in BKK region")
                return flights
            else:
                print(f"❌ Failed to fetch flight data: {response.status_code}")
                return []
        except Exception as e:
            print(f"❌ Error fetching flight data: {str(e)}")
            return []

    def get_latest_radar_frame(self):
        """Get latest weather radar frame from RainViewer API"""
        url = "https://api.rainviewer.com/public/weather-maps.json"
        try:
            response = requests.get(url, timeout=30)
            data = response.json()
            
            radar_frames = data.get("radar", {}).get("past", [])
            if radar_frames:
                return radar_frames[-1]['path'], radar_frames[-1]['time']
            return None, None
        except Exception as e:
            print(f"❌ Error fetching radar data: {str(e)}")
            return None, None

    def calculate_distance(self, lat1, lon1, lat2, lon2):
        """Calculate distance between two points in kilometers"""
        R = 6371.0
        lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
        dlon = lon2 - lon1
        dlat = lat2 - lat1
        a = sin(dlat/2)**2 + cos(lat1)*cos(lat2)*sin(dlon/2)**2
        c = 2 * atan2(sqrt(a), sqrt(1-a))
        return R * c

    def simulate_radar_intensity(self, lat, lon):
        """Simulate radar echo intensity based on geographic patterns"""
        # Create weather zones around BKK
        if 13.9 <= lat <= 14.2 and 100.6 <= lon <= 100.9:  # North approach
            return 45  # Orange zone
        elif 13.6 <= lat <= 13.8 and 101.0 <= lon <= 101.2:  # East sector  
            return 55  # Red zone
        elif 13.3 <= lat <= 13.5 and 100.3 <= lon <= 100.6:  # Southwest
            return 25  # Green zone
        elif self.calculate_distance(lat, lon, BKK_LAT, BKK_LON) < 20:  # Near airport
            return 15  # Light precipitation
        else:
            return 0   # Clear

    def classify_echo_intensity(self, dbz_value):
        """Classify radar echo intensity"""
        for color, thresholds in ECHO_CLASSIFICATIONS.items():
            if thresholds["min_dbz"] <= dbz_value <= thresholds["max_dbz"]:
                return color, thresholds
        return "CLEAR", {"color": "white", "alpha": 0.1}

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

    def process_flight_data(self):
        """Process flight data and create classifications"""
        flights = self.get_flights_near_bkk()
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
            
            # Get radar intensity and classification
            radar_intensity = self.simulate_radar_intensity(lat, lon)
            echo_color, echo_props = self.classify_echo_intensity(radar_intensity)
            
            # Determine aircraft action (simplified)
            if radar_intensity >= 50:
                action = "AVOIDED"
                classification = "COMPLIANT_AVOIDANCE"
            elif radar_intensity >= 40:
                action = "CONTINUED_WITH_CAUTION"
                classification = "RISKY_PENETRATION"
            else:
                action = "CONTINUED_NORMAL"
                classification = "COMPLIANT_GO_THROUGH"

            distance_to_bkk = self.calculate_distance(lat, lon, BKK_LAT, BKK_LON)
            
            flight_info = {
                "callsign": callsign,
                "lat": lat,
                "lon": lon,
                "altitude_ft": int(altitude * 3.28084) if altitude else None,
                "speed_kts": int(velocity * 1.94384) if velocity else None,
                "distance_km": distance_to_bkk,
                "radar_intensity": radar_intensity,
                "echo_color": echo_color,
                "echo_props": echo_props,
                "action": action,
                "classification": classification
            }
            
            flight_classifications.append(flight_info)

        self.flight_data = flight_classifications
        return flight_classifications

    def create_weather_zones(self):
        """Create weather zone polygons for visualization"""
        zones = [
            # North approach (Orange zone)
            {"bounds": [100.6, 100.9, 13.9, 14.2], "intensity": 45, "name": "North Approach"},
            # East sector (Red zone)
            {"bounds": [101.0, 101.2, 13.6, 13.8], "intensity": 55, "name": "East Sector"},
            # Southwest (Green zone)
            {"bounds": [100.3, 100.6, 13.3, 13.5], "intensity": 25, "name": "Southwest"},
            # Airport vicinity (Light)
            {"bounds": [100.6, 100.9, 13.5, 13.9], "intensity": 15, "name": "Airport Area"}
        ]
        
        self.weather_zones = zones
        return zones

    def create_interactive_flight_map(self, save_html=True, save_images=True):
        """Create interactive map with flight data and weather overlay (same style as radar map)"""
        current_time = datetime.datetime.now()
        formatted_time = current_time.strftime("%Y-%m-%d %H:%M:%S")
        
        # Create base folder for flight radar data
        base_folder = "bangkok_flight_radar_data"
        if not os.path.exists(base_folder):
            os.makedirs(base_folder)
        
        # Create subfolder with today's date
        date_folder = os.path.join(base_folder, current_time.strftime("%Y%m%d"))
        if not os.path.exists(date_folder):
            os.makedirs(date_folder)
        
        # Create filenames with timestamp
        time_str = current_time.strftime('%H%M%S')
        html_file = os.path.join(date_folder, f"bangkok_flight_radar_{time_str}.html")
        png_file = os.path.join(date_folder, f"bangkok_flight_radar_{time_str}.png")
        summary_file = os.path.join(date_folder, f"bangkok_flight_radar_{time_str}_data.txt")
        
        try:
            # Create map focused on Bangkok/BKK Airport area (same as weather radar)
            m = folium.Map(
                location=[BANGKOK_CENTER_LAT, BANGKOK_CENTER_LON], 
                zoom_start=10,  # Same zoom as weather radar
                tiles='OpenStreetMap',
                width='100%',
                height='100%'
            )
            
            # Add weather radar overlay if available
            radar_path, radar_timestamp = self.get_latest_radar_frame()
            if radar_path:
                radar_layer = folium.raster_layers.TileLayer(
                    tiles=f"https://tilecache.rainviewer.com{radar_path}/256/{{z}}/{{x}}/{{y}}/2/1_1.png",
                    attr="RainViewer | Thailand Weather Data",
                    name="Weather Radar",
                    overlay=True,
                    control=True,
                    opacity=0.6  # Lower opacity to see flights better
                )
                radar_layer.add_to(m)
            
            # Add weather zones as rectangles (similar to matplotlib version)
            for zone in self.weather_zones:
                bounds = zone["bounds"]
                intensity = zone["intensity"]
                echo_color, echo_props = self.classify_echo_intensity(intensity)
                
                # Create rectangle for weather zone
                folium.Rectangle(
                    bounds=[[bounds[2], bounds[0]], [bounds[3], bounds[1]]],
                    color='gray',
                    fill=True,
                    fillColor=echo_props["color"],
                    fillOpacity=echo_props["alpha"],
                    weight=1,
                    popup=f'{zone["name"]} ({echo_color} - {intensity} dBZ)'
                ).add_to(m)
            
            # Flight classification colors
            classification_colors = {
                "COMPLIANT_GO_THROUGH": "green",
                "COMPLIANT_AVOIDANCE": "blue", 
                "RISKY_PENETRATION": "red",
                "CONSERVATIVE_AVOIDANCE": "orange"
            }
            
            # Add flight positions
            for flight in self.flight_data:
                color = classification_colors.get(flight["classification"], "gray")
                
                # Create flight marker
                folium.Marker(
                    [flight["lat"], flight["lon"]],
                    popup=f"""
                    <b>{flight['callsign']}</b><br>
                    Altitude: {flight['altitude_ft']} ft<br>
                    Speed: {flight['speed_kts']} kts<br>
                    Distance to BKK: {flight['distance_km']:.1f} km<br>
                    Weather: {flight['echo_color']} ({flight['radar_intensity']} dBZ)<br>
                    Action: {flight['action']}<br>
                    Classification: {flight['classification']}
                    """,
                    tooltip=f"{flight['callsign']} - {flight['altitude_ft']}ft",
                    icon=folium.Icon(color=color, icon='plane', prefix='fa')
                ).add_to(m)
            
            # Add BKK Airport marker (same as weather radar style)
            folium.Marker(
                [BKK_LAT, BKK_LON], 
                tooltip="BKK Airport",
                popup="Suvarnabhumi Airport (BKK)",
                icon=folium.Icon(color='red', icon='plane', prefix='fa')
            ).add_to(m)
            
            # Add Bangkok area locations (same as weather radar)
            bangkok_locations = [
                {"name": "Bangkok Downtown", "lat": 13.7563, "lon": 100.5018, "color": "blue"},
                {"name": "BKK Airport", "lat": 13.690, "lon": 100.750, "color": "red"},
                {"name": "Don Mueang Airport", "lat": 13.9126, "lon": 100.6071, "color": "orange"},
                {"name": "Samut Prakan", "lat": 13.5990, "lon": 100.5998, "color": "green"},
                {"name": "Nonthaburi", "lat": 13.8621, "lon": 100.5144, "color": "purple"},
                {"name": "Pathum Thani", "lat": 14.0208, "lon": 100.5250, "color": "darkgreen"}
            ]
            
            for location in bangkok_locations:
                folium.CircleMarker(
                    location=[location["lat"], location["lon"]],
                    radius=8,
                    popup=f"<b>{location['name']}</b>",
                    tooltip=location['name'],
                    color='white',
                    fillColor=location['color'],
                    fill=True,
                    weight=2,
                    fillOpacity=0.8
                ).add_to(m)
            
            # Set map bounds to Bangkok area (same as weather radar)
            m.fit_bounds([
                [BANGKOK_BOUNDS['south'], BANGKOK_BOUNDS['west']],
                [BANGKOK_BOUNDS['north'], BANGKOK_BOUNDS['east']]
            ])
            
            # Add flight statistics
            total_flights = len(self.flight_data)
            risky_flights = sum(1 for f in self.flight_data if f["classification"] == "RISKY_PENETRATION")
            safe_flights = total_flights - risky_flights
            safety_rate = (safe_flights/total_flights*100) if total_flights > 0 else 0
            
            # Add comprehensive title and info (same style as weather radar)
            title_html = f'''
                <div style="position: fixed; 
                            top: 15px; 
                            left: 50%; 
                            transform: translateX(-50%);
                            width: 500px; 
                            height: 100px; 
                            z-index:9999; 
                            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                            color: white;
                            font-family: Arial, sans-serif;
                            font-size: 18px;
                            font-weight: bold;
                            padding: 15px;
                            border-radius: 15px;
                            border: 3px solid #fff;
                            text-align: center;
                            box-shadow: 0 4px 15px rgba(0,0,0,0.3);">
                    ✈️ Bangkok Flight Weather Radar<br>
                    <span style="font-size: 14px; font-weight: normal;">📅 {formatted_time}</span><br>
                    <span style="font-size: 12px; font-weight: normal;">🛰️ Flights: {total_flights} | Safe: {safety_rate:.1f}%</span><br>
                    <span style="font-size: 10px; font-weight: normal;">📍 Real-time Flight & Weather Data</span>
                </div>
            '''
            m.get_root().html.add_child(folium.Element(title_html))
            
            # Add CSS for better appearance (same as weather radar)
            css_style = '''
                <style>
                    .leaflet-container {
                        font-family: Arial, sans-serif;
                    }
                    .leaflet-popup-content {
                        font-weight: bold;
                    }
                </style>
            '''
            m.get_root().html.add_child(folium.Element(css_style))
            
            # Save HTML file
            if save_html:
                m.save(html_file)
                print(f"💾 Saved HTML: {os.path.basename(html_file)}")
            
            # Take screenshot if driver is available
            if save_images and self.driver:
                self.capture_screenshot_png(html_file, png_file, formatted_time)
            
            # Create detailed summary file
            with open(summary_file, 'w', encoding='utf-8') as f:
                f.write(f"✈️ BANGKOK FLIGHT WEATHER RADAR DATA\n")
                f.write(f"=" * 50 + "\n\n")
                f.write(f"📅 Collection Time: {formatted_time}\n")
                f.write(f"🛰️ Data Sources: OpenSky Network + RainViewer API\n")
                f.write(f"🗺️ Geographic Focus: Bangkok Metropolitan Area\n")
                f.write(f"📍 Map Center: {BANGKOK_CENTER_LAT}°N, {BANGKOK_CENTER_LON}°E\n")
                f.write(f"✈️ BKK Airport: {BKK_LAT}°N, {BKK_LON}°E\n")
                f.write(f"🔍 Zoom Level: 10 (High Detail)\n")
                f.write(f"📁 HTML File: {os.path.basename(html_file)}\n")
                f.write(f"🖼️ PNG File: {os.path.basename(png_file)}\n\n")
                f.write(f"FLIGHT STATISTICS:\n")
                f.write(f"✈️ Total Arrivals: {total_flights}\n")
                f.write(f"✅ Safe Operations: {safe_flights}\n")
                f.write(f"🚨 Risky Penetrations: {risky_flights}\n")
                f.write(f"📊 Safety Rate: {safety_rate:.1f}%\n\n")
                f.write(f"FLIGHT DETAILS:\n")
                for i, flight in enumerate(self.flight_data, 1):
                    f.write(f"{i}. {flight['callsign']} | {flight['echo_color']} ({flight['radar_intensity']} dBZ)\n")
                    f.write(f"   📍 {flight['lat']:.3f}°N, {flight['lon']:.3f}°E | {flight['altitude_ft']}ft\n")
                    f.write(f"   🛡️ {flight['classification']} | {flight['action']}\n\n")
            
            print(f"✅ Bangkok flight radar data saved: {formatted_time}")
            return html_file
            
        except Exception as e:
            print(f"❌ Error creating Bangkok flight radar map: {str(e)}")
            return None

    def capture_screenshot_png(self, html_file, png_file, formatted_time):
        """Capture PNG screenshot of the Bangkok flight map"""
        try:
            # Load the HTML file
            file_url = f"file://{os.path.abspath(html_file)}"
            self.driver.get(file_url)
            
            # Wait for map to load
            print(f"📸 Taking flight radar screenshot for {formatted_time}...")
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CLASS_NAME, "leaflet-container"))
            )
            
            # Additional wait for tiles and flight data to load
            time.sleep(5)
            
            # Take screenshot as PNG with high resolution
            self.driver.set_window_size(1920, 1080)
            self.driver.save_screenshot(png_file)
            print(f"🖼️ Saved flight radar PNG: {os.path.basename(png_file)}")
                
        except Exception as e:
            print(f"❌ Error capturing flight radar screenshot: {str(e)}")

    def run_continuous_flight_monitoring(self, interval_minutes=10):
        """Run continuous flight monitoring with interactive map creation"""
        print(f"🔄 Starting Bangkok flight weather radar monitoring every {interval_minutes} minutes.")
        print(f"🎯 Focus: Bangkok & BKK Airport flight tracking with weather overlay")
        print(f"💾 Data saved as: HTML + PNG + Summary (same format as weather radar)")
        print(f"🛑 Press Ctrl+C to stop. Data will be saved to 'bangkok_flight_radar_data' folder.")
        
        collection_count = 0
        
        try:
            while True:
                current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                collection_count += 1
                
                print(f"\n🕐 [{current_time}] Flight collection #{collection_count}")
                print("-" * 50)
                
                # Process flight data
                self.create_weather_zones()
                flights = self.process_flight_data()
                
                if flights:
                    # Create interactive map
                    html_file = self.create_interactive_flight_map()
                    if html_file:
                        print(f"✅ Flight collection #{collection_count} successful")
                    else:
                        print(f"❌ Flight collection #{collection_count} failed")
                else:
                    print("📊 No arrival flights detected")
                
                next_time = datetime.datetime.now() + datetime.timedelta(minutes=interval_minutes)
                print(f"⏰ Next flight collection at: {next_time.strftime('%H:%M:%S')}")
                
                time.sleep(interval_minutes * 60)
                
        except KeyboardInterrupt:
            print(f"\n🛑 Flight monitoring stopped after {collection_count} collections")
        finally:
            if self.driver:
                self.driver.quit()

    def create_single_flight_map(self):
        """Create single flight map with current data"""
        print("🗺️ Creating single flight radar map with weather overlay...")
        self.load_thailand_map()
        self.create_weather_zones()
        flights = self.process_flight_data()
        
        if flights:
            html_file = self.create_interactive_flight_map()
            if html_file:
                print(f"✅ Interactive flight map created: {html_file}")
                return html_file
            else:
                print("❌ Failed to create interactive map")
                return None
        else:
            print("📊 No flights to display")
            return None

    def print_flight_summary(self):
        """Print detailed flight summary"""
        if not self.flight_data:
            print("📊 No flight data to summarize")
            return
        
        print("\n" + "="*80)
        print("✈️ FLIGHT WEATHER INTERACTION SUMMARY")
        print("="*80)
        
        for i, flight in enumerate(self.flight_data, 1):
            status_icon = "🚨" if flight["classification"] == "RISKY_PENETRATION" else "✅"
            
            print(f"\n{i}. {status_icon} {flight['callsign']} | {flight['echo_color']} ECHO ({flight['radar_intensity']} dBZ)")
            print(f"   📍 Position: {flight['lat']:.3f}°N, {flight['lon']:.3f}°E")
            print(f"   ✈️ Altitude: {flight['altitude_ft']} ft | Speed: {flight['speed_kts']} kts")
            print(f"   🎯 Distance to BKK: {flight['distance_km']:.1f} km")
            print(f"   🛡️ Action: {flight['action']}")
            print(f"   📊 Classification: {flight['classification']}")

    def __del__(self):
        """Cleanup driver when object is destroyed"""
        if self.driver:
            self.driver.quit()

def main():
    print("\n" + "="*70)
    print("🇹🇭 ENHANCED BANGKOK FLIGHT WEATHER RADAR")
    print("="*70)
    print("✨ Features:")
    print("   📊 Real-time flight tracking with weather overlay")
    print("   🗺️ Interactive maps (same style as weather radar)")
    print("   💾 Saves HTML + PNG + Summary files")
    print("   ✈️ Flight classification based on weather interaction")
    print("   🌦️ Integrated weather radar data")
    print("   📱 High-quality screenshots for analysis")
    
    # Get map file path
    map_path = input("\n📁 Enter path to thailand_outline.csv (or press Enter to use simplified): ").strip()
    if not map_path:
        map_path = None
    
    # Create enhanced radar system
    flight_radar = EnhancedBangkokFlightRadar(map_path)
    
    print("\n📋 Options:")
    print("   1. Single interactive flight map (current flights)")
    print("   2. Continuous flight monitoring with maps")
    print("   3. Create flight map + traditional matplotlib plot")
    
    choice = input("\n🎯 Enter your choice (1, 2, or 3): ")
    
    if choice == "1":
        print("🗺️ Creating single interactive flight radar map...")
        html_file = flight_radar.create_single_flight_map()
        if html_file:
            flight_radar.print_flight_summary()
            print(f"\n📂 Open this file in your browser: {html_file}")
        
    elif choice == "2":
        try:
            interval = input("⏱️ Enter monitoring interval in minutes (default: 10): ")
            interval = int(interval) if interval.strip() else 10
            if interval < 5:
                print("⚠️ Minimum interval is 5 minutes to avoid server overload.")
                interval = 5
            flight_radar.run_continuous_flight_monitoring(interval)
        except ValueError:
            print("❌ Invalid input. Using default (10 minutes).")
            flight_radar.run_continuous_flight_monitoring(10)
    
    elif choice == "3":
        print("🗺️ Creating both interactive map and matplotlib plot...")
        
        # Create interactive map
        html_file = flight_radar.create_single_flight_map()
        
        # Also create traditional matplotlib plot
        if flight_radar.thailand_segments or flight_radar.load_thailand_map():
            flight_radar.create_weather_zones()
            flight_radar.process_flight_data()
            flight_radar.plot_traditional_map("enhanced_flight_radar_matplotlib.png")
            flight_radar.print_flight_summary()
            
            if html_file:
                print(f"\n📂 Interactive map: {html_file}")
                print(f"📂 Matplotlib plot: enhanced_flight_radar_matplotlib.png")
        
    else:
        print("❌ Invalid choice. Creating single interactive map...")
        flight_radar.create_single_flight_map()

def plot_traditional_map(self, save_file="bangkok_flight_radar_traditional.png"):
    """Create traditional matplotlib plot (enhanced version of original)"""
    # Set up the plot with larger figure
    plt.figure(figsize=(16, 14))
    plt.gca().set_aspect('equal')
    
    # Plot Thailand outline with better styling
    print("🗺️ Drawing Thailand map...")
    for i, (lon_seg, lat_seg) in enumerate(self.thailand_segments):
        plt.plot(lon_seg, lat_seg, color='black', linewidth=2, alpha=0.9, zorder=1)

    # Focus on Bangkok area for better detail
    plt.xlim(BANGKOK_BOUNDS['west']-0.2, BANGKOK_BOUNDS['east']+0.2)
    plt.ylim(BANGKOK_BOUNDS['south']-0.2, BANGKOK_BOUNDS['north']+0.2)
    
    # Add weather zones with better colors
    print("🌦️ Adding weather zones...")
    for zone in self.weather_zones:
        bounds = zone["bounds"]
        intensity = zone["intensity"]
        echo_color, echo_props = self.classify_echo_intensity(intensity)
        
        # Create rectangle for weather zone
        rect = patches.Rectangle(
            (bounds[0], bounds[2]),  # (x, y) bottom-left
            bounds[1] - bounds[0],   # width
            bounds[3] - bounds[2],   # height
            linewidth=2,
            edgecolor='darkgray',
            facecolor=echo_props["color"],
            alpha=echo_props["alpha"],
            zorder=2,
            label=f'{zone["name"]} ({echo_color})'
        )
        plt.gca().add_patch(rect)

    # Plot flight data with enhanced markers
    print("✈️ Adding flight positions...")
    classification_colors = {
        "COMPLIANT_GO_THROUGH": "green",
        "COMPLIANT_AVOIDANCE": "blue", 
        "RISKY_PENETRATION": "red",
        "CONSERVATIVE_AVOIDANCE": "orange"
    }
    
    classification_markers = {
        "COMPLIANT_GO_THROUGH": "^",
        "COMPLIANT_AVOIDANCE": "s", 
        "RISKY_PENETRATION": "D",
        "CONSERVATIVE_AVOIDANCE": "o"
    }
    
    for flight in self.flight_data:
        color = classification_colors.get(flight["classification"], "gray")
        marker = classification_markers.get(flight["classification"], "^")
        
        # Plot flight position with larger, more visible markers
        plt.scatter(flight["lon"], flight["lat"], 
                   c=color, s=150, marker=marker, 
                   edgecolors='black', linewidth=2,
                   alpha=0.9, zorder=5)
        
        # Add enhanced flight label
        plt.annotate(f'{flight["callsign"]}\n{flight["altitude_ft"]}ft\n{flight["echo_color"]}', 
                    (flight["lon"], flight["lat"]),
                    xytext=(8, 8), textcoords='offset points',
                    fontsize=9, fontweight='bold',
                    bbox=dict(boxstyle="round,pad=0.4", facecolor=color, alpha=0.8, edgecolor='black'))

    # Add enhanced BKK Airport marker
    plt.scatter(BKK_LON, BKK_LAT, c='red', s=300, marker='s', 
               edgecolors='black', linewidth=3, zorder=10,
               label='BKK Airport')
    plt.annotate('BKK Airport\n(Suvarnabhumi)', (BKK_LON, BKK_LAT),
                xytext=(15, 15), textcoords='offset points',
                fontsize=12, fontweight='bold',
                bbox=dict(boxstyle="round,pad=0.6", facecolor='white', alpha=0.95, edgecolor='red', linewidth=2))

    # Add Bangkok center and other airports
    plt.scatter(BANGKOK_CENTER_LON, BANGKOK_CENTER_LAT, c='blue', s=150, 
               marker='o', edgecolors='black', linewidth=2, zorder=10,
               label='Bangkok Center')
    
    # Don Mueang Airport
    plt.scatter(100.6071, 13.9126, c='orange', s=200, marker='s', 
               edgecolors='black', linewidth=2, zorder=10,
               label='Don Mueang Airport')

    # Enhanced formatting
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    plt.title(f'Bangkok Flight Weather Radar - Enhanced Interactive Style\n{current_time}', 
             fontsize=18, fontweight='bold', pad=20)
    plt.xlabel('Longitude', fontsize=14, fontweight='bold')
    plt.ylabel('Latitude', fontsize=14, fontweight='bold')
    
    # Enhanced grid
    plt.grid(True, alpha=0.4, linestyle='--', linewidth=0.8)
    plt.tick_params(labelsize=12)

    # Create comprehensive legend
    legend_elements = [
        plt.Line2D([0], [0], marker='^', color='w', markerfacecolor='green', 
                  markersize=12, markeredgecolor='black', markeredgewidth=1, label='Safe Go-Through'),
        plt.Line2D([0], [0], marker='D', color='w', markerfacecolor='red', 
                  markersize=12, markeredgecolor='black', markeredgewidth=1, label='Risky Penetration'),
        plt.Line2D([0], [0], marker='s', color='w', markerfacecolor='blue', 
                  markersize=12, markeredgecolor='black', markeredgewidth=1, label='Compliant Avoidance'),
        plt.Line2D([0], [0], marker='s', color='w', markerfacecolor='red', 
                  markersize=12, markeredgecolor='black', markeredgewidth=1, label='BKK Airport'),
        plt.Line2D([0], [0], marker='s', color='w', markerfacecolor='orange', 
                  markersize=12, markeredgecolor='black', markeredgewidth=1, label='Don Mueang Airport'),
        plt.Rectangle((0,0), 1, 1, facecolor='green', alpha=0.3, edgecolor='darkgray', label='Light Weather (Green)'),
        plt.Rectangle((0,0), 1, 1, facecolor='orange', alpha=0.5, edgecolor='darkgray', label='Heavy Weather (Orange)'),
        plt.Rectangle((0,0), 1, 1, facecolor='red', alpha=0.6, edgecolor='darkgray', label='Severe Weather (Red)')
    ]
    
    plt.legend(handles=legend_elements, loc='upper left', fontsize=11, framealpha=0.95)

    # Add enhanced statistics box
    if self.flight_data:
        total_flights = len(self.flight_data)
        risky_flights = sum(1 for f in self.flight_data if f["classification"] == "RISKY_PENETRATION")
        safe_flights = total_flights - risky_flights
        
        stats_text = f"""Flight Statistics:
Total Arrivals: {total_flights}
Safe Operations: {safe_flights}
Risky Penetrations: {risky_flights}
Safety Rate: {(safe_flights/total_flights*100):.1f}%

Map Style: Enhanced Interactive
Data Sources: OpenSky + RainViewer"""
        
        plt.text(0.02, 0.02, stats_text, transform=plt.gca().transAxes,
                fontsize=11, verticalalignment='bottom',
                bbox=dict(boxstyle="round,pad=0.6", facecolor='lightblue', alpha=0.9, edgecolor='navy'))

    # Add compass rose
    plt.text(0.95, 0.95, 'N ↑', transform=plt.gca().transAxes,
            fontsize=14, fontweight='bold', ha='center', va='center',
            bbox=dict(boxstyle="round,pad=0.3", facecolor='white', alpha=0.8))

    plt.tight_layout()
    
    # Save with high DPI
    plt.savefig(save_file, dpi=300, bbox_inches='tight', facecolor='white')
    print(f"💾 Enhanced matplotlib map saved as: {save_file}")
    
    plt.show()

# Add the method to the class
EnhancedBangkokFlightRadar.plot_traditional_map = plot_traditional_map

if __name__ == "__main__":
    main()