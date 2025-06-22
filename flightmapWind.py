#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Wind-Enhanced Weather Flight Radar with METAR Data
Fetches real-time wind data from VTBS (Bangkok Suvarnabhumi) METAR reports
Saves HTML maps and PNG screenshots in organized folders
"""

import matplotlib.pyplot as plt
import numpy as np
import requests
import datetime
import json
from math import sin, cos, sqrt, atan2, radians, degrees
import time
import folium
import os
import re
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
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

class SimpleWindWeatherRadar:
    def __init__(self):
        self.flight_data = []
        self.weather_data = None
        self.wind_data = None
        self.metar_raw = ""
        
        # Create output directories
        self.setup_directories()
        
        # Fetch initial wind data from METAR
        self.update_wind_from_metar()
        
    def setup_directories(self):
        """Create organized folder structure for outputs"""
        # Base directory with today's date
        today = datetime.datetime.now().strftime('%Y-%m-%d')
        self.base_dir = f"flight_radar_data/{today}"
        self.html_dir = f"{self.base_dir}/html"
        self.png_dir = f"{self.base_dir}/screenshots"
        
        # Create directories if they don't exist
        for directory in [self.base_dir, self.html_dir, self.png_dir]:
            os.makedirs(directory, exist_ok=True)
        
        print(f"Output directories created:")
        print(f"  - HTML files: {self.html_dir}")
        print(f"  - Screenshots: {self.png_dir}")
        
    def parse_metar_wind(self, metar_text):
        """Parse wind information from METAR text"""
        # Wind pattern: dddssKT or dddssGggKT (direction, speed, optional gust)
        # VRB for variable direction
        wind_pattern = r'(\d{3}|VRB)(\d{2,3})(G(\d{2,3}))?KT'
        
        match = re.search(wind_pattern, metar_text)
        if match:
            direction = match.group(1)
            speed = int(match.group(2))
            gust = int(match.group(4)) if match.group(4) else None
            
            # Handle variable wind direction
            if direction == 'VRB':
                direction = 0  # Use 0 for variable
                print("Wind direction is variable")
            else:
                direction = int(direction)
            
            return {
                'direction': direction,
                'speed_kt': speed,
                'gust_kt': gust
            }
        
        # Check for calm winds
        if 'CALM' in metar_text or '00000KT' in metar_text:
            return {
                'direction': 0,
                'speed_kt': 0,
                'gust_kt': None
            }
        
        return None
    
    def update_wind_from_metar(self):
        """Fetch and parse wind data from VTBS METAR"""
        # Using the aviationweather.gov API endpoint
        url = "https://aviationweather.gov/api/data/metar?ids=VTBS&format=json&taf=false"
        
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                
                if data and len(data) > 0:
                    metar_data = data[0]
                    self.metar_raw = metar_data.get('rawOb', '')
                    
                    # Parse wind from raw METAR
                    wind_info = self.parse_metar_wind(self.metar_raw)
                    
                    if wind_info:
                        # Convert knots to m/s (1 knot = 0.514444 m/s)
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
                        
                        print(f"\nMETAR Wind Data from VTBS:")
                        print(f"Raw METAR: {self.metar_raw}")
                        print(f"Wind: {wind_info['speed_kt']} kt ({speed_mps:.1f} m/s) from {wind_info['direction']}°")
                        if wind_info['gust_kt']:
                            print(f"Gusts: {wind_info['gust_kt']} kt ({gust_mps:.1f} m/s)")
                        
                        return True
                    else:
                        print("Could not parse wind data from METAR")
                else:
                    print("No METAR data received")
                    
        except Exception as e:
            print(f"Error fetching METAR data: {str(e)}")
        
        # Fallback to default wind data if METAR fetch fails
        print("Using default wind data as fallback")
        self.wind_data = {
            "surface": {
                "speed_mps": 5.2,
                "speed_kt": 10,
                "direction": 230,
                "gust_mps": None,
                "gust_kt": None,
                "timestamp": datetime.datetime.now(),
                "raw_metar": "NO METAR DATA AVAILABLE"
            }
        }
        return False

    def get_flights_near_bkk(self):
        """Fetch flights from OpenSky Network"""
        url = "https://opensky-network.org/api/states/all"
        try:
            response = requests.get(url, params=BBOX, timeout=30)
            if response.status_code == 200:
                data = response.json()
                flights = data.get("states", [])
                print(f"Found {len(flights)} flights")
                return flights
            else:
                print(f"Failed to fetch flight data: {response.status_code}")
                return []
        except Exception as e:
            print(f"Error fetching flight data: {str(e)}")
            return []

    def get_weather_data(self):
        """Get weather radar data"""
        try:
            url = "https://api.rainviewer.com/public/weather-maps.json"
            response = requests.get(url, timeout=30)
            data = response.json()
            
            # Get latest radar frame
            past_radar = data.get("radar", {}).get("past", [])
            if past_radar:
                latest_frame = past_radar[-1]
                self.weather_data = {
                    'path': latest_frame['path'],
                    'time': datetime.datetime.fromtimestamp(latest_frame['time'])
                }
                print("Weather radar data loaded")
                return True
            return False
        except Exception as e:
            print(f"Error fetching weather: {str(e)}")
            return False

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
        """Calculate headwind/tailwind component"""
        # Convert to radians
        flight_heading_rad = radians(flight_heading)
        wind_direction_rad = radians(wind_direction)
        
        # Calculate relative wind angle
        relative_wind = wind_direction_rad - flight_heading_rad
        
        # Calculate components
        headwind_component = wind_speed * cos(relative_wind)
        crosswind_component = wind_speed * sin(relative_wind)
        
        return headwind_component, crosswind_component

    def is_arrival_flight(self, flight):
        """Check if flight is arriving"""
        lat, lon, altitude = flight[6], flight[5], flight[7]
        
        if not all([lat, lon, altitude]):
            return False
        
        distance = self.calculate_distance(lat, lon, BKK_LAT, BKK_LON)
        is_below_10k = altitude and altitude < 3048  # Below 10,000 feet
        is_within_80km = distance < 80
        
        return is_below_10k and is_within_80km

    def process_flights(self):
        """Process flight data with wind analysis"""
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
            
            # Calculate heading to BKK
            heading_to_bkk = self.calculate_heading(lat, lon, BKK_LAT, BKK_LON)
            
            # Calculate wind components
            headwind, crosswind = self.calculate_wind_component(
                heading_to_bkk,
                self.wind_data["surface"]["direction"],
                self.wind_data["surface"]["speed_mps"]
            )
            
            # Determine wind condition
            if headwind > 5:
                wind_condition = "STRONG_HEADWIND"
                wind_color = "red"
            elif headwind > 2:
                wind_condition = "MODERATE_HEADWIND"
                wind_color = "orange"
            elif headwind > -2:
                wind_condition = "CALM"
                wind_color = "green"
            elif headwind > -5:
                wind_condition = "MODERATE_TAILWIND"
                wind_color = "lightgreen"
            else:
                wind_condition = "STRONG_TAILWIND"
                wind_color = "darkgreen"
            
            distance_to_bkk = self.calculate_distance(lat, lon, BKK_LAT, BKK_LON)
            
            flight_info = {
                "callsign": callsign,
                "lat": lat,
                "lon": lon,
                "altitude_ft": int(altitude * 3.28084) if altitude else 0,
                "speed_kts": int(velocity * 1.94384) if velocity else 0,
                "distance_km": distance_to_bkk,
                "heading_to_bkk": heading_to_bkk,
                "headwind_component": headwind,
                "crosswind_component": crosswind,
                "wind_condition": wind_condition,
                "wind_color": wind_color
            }
            
            self.flight_data.append(flight_info)
        
        print(f"Processed {len(self.flight_data)} arrival flights")
        return self.flight_data

    def create_map(self):
        """Create the interactive map"""
        current_time = datetime.datetime.now()
        
        # Create map centered on BKK with closer zoom for airport area
        m = folium.Map(
            location=[BKK_LAT, BKK_LON], 
            zoom_start=11,  # Closer zoom for airport area
            tiles='OpenStreetMap'
        )
        
        # Add weather radar if available
        if self.weather_data:
            radar_layer = folium.raster_layers.TileLayer(
                tiles=f"https://tilecache.rainviewer.com{self.weather_data['path']}/256/{{z}}/{{x}}/{{y}}/2/1_1.png",
                attr="RainViewer",
                name="Weather Radar",
                overlay=True,
                control=True,
                opacity=0.6
            )
            radar_layer.add_to(m)
        
        # Add wind indicator with METAR data
        wind_speed_kts = self.wind_data['surface']['speed_kt']
        wind_dir = self.wind_data['surface']['direction']
        gust_info = f"<br>Gusts: {self.wind_data['surface']['gust_kt']} kts" if self.wind_data['surface']['gust_kt'] else ""
        metar_time = self.wind_data['surface'].get('metar_time', 'N/A')
        
        # Add a wind indicator with METAR info
        wind_html = f"""
        <div style="position: fixed; top: 10px; right: 10px; 
                    background: white; padding: 15px; border: 2px solid black;
                    border-radius: 5px; z-index: 1000; min-width: 200px;">
            <b>VTBS METAR Wind:</b><br>
            {wind_speed_kts} kts from {wind_dir}°{gust_info}<br>
            <small>Report: {metar_time}</small><br>
            <small style="color: #666;">Raw: {self.metar_raw[:50]}...</small>
        </div>
        """
        m.get_root().html.add_child(folium.Element(wind_html))
        
        # Add flight markers
        for flight in self.flight_data:
            popup_text = f"""
            <b>{flight['callsign']}</b><br>
            Altitude: {flight['altitude_ft']} ft<br>
            Speed: {flight['speed_kts']} kts<br>
            Distance: {flight['distance_km']:.1f} km<br>
            <br>
            <b>Wind Analysis:</b><br>
            Headwind: {flight['headwind_component']:.1f} m/s<br>
            Crosswind: {flight['crosswind_component']:.1f} m/s<br>
            Condition: {flight['wind_condition']}
            """
            
            folium.Marker(
                [flight["lat"], flight["lon"]],
                popup=popup_text,
                tooltip=f"{flight['callsign']} - {flight['wind_condition']}",
                icon=folium.Icon(color=flight['wind_color'], icon='plane', prefix='fa')
            ).add_to(m)
        
        # Add BKK Airport with larger icon
        folium.Marker(
            [BKK_LAT, BKK_LON], 
            popup=f"Suvarnabhumi Airport (BKK/VTBS)<br>Wind: {wind_speed_kts} kt from {wind_dir}°",
            icon=folium.Icon(color='red', icon='star', prefix='fa')
        ).add_to(m)
        
        # Add approach pattern indicators (common approach paths)
        # Add circles for distance reference
        for distance in [10, 20, 30, 50]:  # km
            folium.Circle(
                location=[BKK_LAT, BKK_LON],
                radius=distance * 1000,  # Convert to meters
                color='blue',
                fill=False,
                weight=1,
                opacity=0.5,
                popup=f"{distance} km from BKK"
            ).add_to(m)
        
        # Add title
        title_html = f"""
        <div style="position: fixed; top: 10px; left: 50%; transform: translateX(-50%);
                    background: #2c3e50; color: white; padding: 10px 20px;
                    border-radius: 5px; z-index: 1000;">
            <h3 style="margin: 0;">Bangkok Wind & Weather Flight Radar</h3>
            <p style="margin: 0; font-size: 12px;">{current_time.strftime('%Y-%m-%d %H:%M:%S')} (METAR-based wind data)</p>
        </div>
        """
        m.get_root().html.add_child(folium.Element(title_html))
        
        # Generate filename with timestamp
        timestamp = current_time.strftime('%Y%m%d_%H%M%S')
        base_filename = f"wind_weather_map_{timestamp}"
        
        # Save HTML in the html directory
        html_filename = f"{self.html_dir}/{base_filename}.html"
        m.save(html_filename)
        
        print(f"\nHTML map saved as: {html_filename}")
        
        # Try to capture screenshot
        png_filename = self.capture_screenshot(html_filename, base_filename)
        
        print(f"Total flights shown: {len(self.flight_data)}")
        
        # Print summary
        headwind_count = sum(1 for f in self.flight_data if 'HEADWIND' in f['wind_condition'])
        tailwind_count = sum(1 for f in self.flight_data if 'TAILWIND' in f['wind_condition'])
        
        print(f"\nWind Analysis Summary:")
        print(f"- Flights with headwind: {headwind_count}")
        print(f"- Flights with tailwind: {tailwind_count}")
        print(f"- Surface wind: {wind_speed_kts} kt from {wind_dir}°")
        if self.wind_data['surface']['gust_kt']:
            print(f"- Gusts up to: {self.wind_data['surface']['gust_kt']} kt")
        
        return html_filename, png_filename

    def capture_screenshot(self, html_path, base_filename):
        """Capture a PNG screenshot of the map using selenium or matplotlib fallback"""
        png_filename = f"{self.png_dir}/{base_filename}.png"
        
        try:
            # Try using selenium for screenshot
            print("\nAttempting to capture screenshot with selenium...")
            
            # Setup Chrome options
            chrome_options = Options()
            chrome_options.add_argument("--headless")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--window-size=1920,1080")
            
            # Create driver
            driver = webdriver.Chrome(options=chrome_options)
            
            # Load the HTML file
            full_path = os.path.abspath(html_path)
            driver.get(f"file://{full_path}")
            
            # Wait for map to load
            time.sleep(3)
            
            # Take screenshot
            driver.save_screenshot(png_filename)
            driver.quit()
            
            print(f"Screenshot saved as: {png_filename}")
            return png_filename
            
        except Exception as e:
            print(f"Selenium screenshot failed: {str(e)}")
            print("Falling back to matplotlib static map...")
            
            # Fallback: Create a static map with matplotlib
            return self.create_static_map(base_filename)
    
    def create_static_map(self, base_filename):
        """Create a static map using matplotlib as fallback"""
        fig, ax = plt.subplots(1, 1, figsize=(12, 10))
        
        # Set map bounds around BKK
        ax.set_xlim(BKK_LON - 0.5, BKK_LON + 0.5)
        ax.set_ylim(BKK_LAT - 0.4, BKK_LAT + 0.4)
        
        # Plot BKK airport
        ax.plot(BKK_LON, BKK_LAT, 'r*', markersize=20, label='BKK Airport')
        
        # Plot distance circles
        for distance in [10, 20, 30, 50]:
            circle = plt.Circle((BKK_LON, BKK_LAT), distance/111.0, 
                               fill=False, color='blue', alpha=0.3)
            ax.add_patch(circle)
        
        # Plot flights
        for flight in self.flight_data:
            color_map = {
                'red': 'Strong Headwind',
                'orange': 'Moderate Headwind',
                'green': 'Calm',
                'lightgreen': 'Moderate Tailwind',
                'darkgreen': 'Strong Tailwind'
            }
            
            ax.plot(flight['lon'], flight['lat'], 'o', 
                   color=flight['wind_color'], markersize=8)
            
            # Add callsign label
            ax.annotate(flight['callsign'], 
                       (flight['lon'], flight['lat']),
                       xytext=(5, 5), textcoords='offset points',
                       fontsize=8, alpha=0.7)
        
        # Add wind information
        wind_text = f"Wind: {self.wind_data['surface']['speed_kt']} kt from {self.wind_data['surface']['direction']}°"
        if self.wind_data['surface']['gust_kt']:
            wind_text += f" (Gusts: {self.wind_data['surface']['gust_kt']} kt)"
        
        ax.text(0.02, 0.98, wind_text, transform=ax.transAxes,
                verticalalignment='top', bbox=dict(boxstyle='round', facecolor='white'))
        
        # Labels and title
        ax.set_xlabel('Longitude')
        ax.set_ylabel('Latitude')
        ax.set_title(f'Bangkok Airport Wind Analysis - {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
        ax.grid(True, alpha=0.3)
        
        # Add legend
        handles = []
        labels = []
        for color, label in [('red', 'Strong Headwind'), ('orange', 'Moderate Headwind'),
                           ('green', 'Calm'), ('lightgreen', 'Moderate Tailwind'),
                           ('darkgreen', 'Strong Tailwind')]:
            handles.append(plt.Line2D([0], [0], marker='o', color='w', 
                                    markerfacecolor=color, markersize=8))
            labels.append(label)
        
        ax.legend(handles, labels, loc='lower right')
        
        # Save the plot
        png_filename = f"{self.png_dir}/{base_filename}_static.png"
        plt.savefig(png_filename, dpi=150, bbox_inches='tight')
        plt.close()
        
        print(f"Static map saved as: {png_filename}")
        return png_filename

    def create_summary_report(self):
        """Create a summary report for the day"""
        timestamp = datetime.datetime.now()
        report_filename = f"{self.base_dir}/daily_summary_{timestamp.strftime('%Y%m%d')}.txt"
        
        with open(report_filename, 'a') as f:
            f.write(f"\n{'='*60}\n")
            f.write(f"Flight Radar Summary - {timestamp.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"{'='*60}\n\n")
            
            f.write(f"Wind Conditions:\n")
            f.write(f"- Speed: {self.wind_data['surface']['speed_kt']} kt ")
            f.write(f"({self.wind_data['surface']['speed_mps']:.1f} m/s)\n")
            f.write(f"- Direction: {self.wind_data['surface']['direction']}°\n")
            if self.wind_data['surface']['gust_kt']:
                f.write(f"- Gusts: {self.wind_data['surface']['gust_kt']} kt\n")
            f.write(f"- METAR: {self.metar_raw}\n\n")
            
            f.write(f"Flight Summary:\n")
            f.write(f"- Total arrival flights: {len(self.flight_data)}\n")
            
            # Count wind conditions
            conditions = {}
            for flight in self.flight_data:
                cond = flight['wind_condition']
                conditions[cond] = conditions.get(cond, 0) + 1
            
            for cond, count in conditions.items():
                f.write(f"- {cond}: {count} flights\n")
            
            f.write(f"\nFlight Details:\n")
            for flight in sorted(self.flight_data, key=lambda x: x['distance_km']):
                f.write(f"- {flight['callsign']}: {flight['distance_km']:.1f} km, ")
                f.write(f"{flight['altitude_ft']} ft, {flight['wind_condition']}\n")
        
        print(f"\nSummary report updated: {report_filename}")

    def run_single_analysis(self):
        """Run a single analysis"""
        print("\nFetching data...")
        
        # Update wind data from METAR
        print("Updating wind data from VTBS METAR...")
        self.update_wind_from_metar()
        
        # Get weather data
        self.get_weather_data()
        
        # Process flights
        self.process_flights()
        
        if self.flight_data:
            # Create map and screenshot
            html_file, png_file = self.create_map()
            
            # Create summary report
            self.create_summary_report()
            
            print(f"\nFiles saved in:")
            print(f"  - HTML: {html_file}")
            print(f"  - PNG: {png_file}")
            print(f"\nOpen the HTML file in your browser for interactive map")
        else:
            print("\nNo arrival flights found in the area")

    def run_continuous(self, interval_minutes=10):
        """Run continuous monitoring"""
        print(f"\nStarting continuous monitoring every {interval_minutes} minutes")
        print("Press Ctrl+C to stop\n")
        
        count = 0
        try:
            while True:
                count += 1
                print(f"\n--- Update #{count} at {datetime.datetime.now().strftime('%H:%M:%S')} ---")
                
                # Update wind data every cycle
                self.update_wind_from_metar()
                
                self.get_weather_data()
                self.process_flights()
                
                if self.flight_data:
                    html_file, png_file = self.create_map()
                    self.create_summary_report()
                else:
                    print("No arrival flights found")
                
                print(f"\nNext update in {interval_minutes} minutes...")
                time.sleep(interval_minutes * 60)
                
        except KeyboardInterrupt:
            print(f"\nMonitoring stopped after {count} updates")

def main():
    print("\n=== WIND & WEATHER FLIGHT RADAR WITH METAR DATA ===")
    print("\nFeatures:")
    print("- Real-time flight tracking near Bangkok")
    print("- Live wind data from VTBS METAR reports")
    print("- Wind analysis (headwind/tailwind)")
    print("- Weather radar overlay")
    print("- Color-coded flights by wind condition")
    print("- Organized file storage with HTML and PNG outputs")
    
    # Check for selenium/chrome driver
    print("\nNote: For best screenshot quality, install Chrome and ChromeDriver")
    print("Without it, will use matplotlib for static maps")
    
    radar = SimpleWindWeatherRadar()
    
    print("\nOptions:")
    print("1. Single analysis")
    print("2. Continuous monitoring")
    
    choice = input("\nEnter choice (1 or 2): ")
    
    if choice == "1":
        radar.run_single_analysis()
    elif choice == "2":
        interval = input("Enter interval in minutes (default 10): ")
        interval = int(interval) if interval.strip() else 10
        radar.run_continuous(interval)
    else:
        print("Invalid choice")

if __name__ == "__main__":
    main()