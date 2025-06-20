#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Simplified Wind-Enhanced Weather Flight Radar
Focus on core functionality with minimal complexity
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
        self.wind_data = {
            "surface": {
                "speed_mps": 5.2,
                "direction": 230,
                "timestamp": datetime.datetime.now()
            }
        }
        
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
                print("Weather data loaded")
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
        
        # Create map
        m = folium.Map(
            location=[BANGKOK_CENTER_LAT, BANGKOK_CENTER_LON], 
            zoom_start=10,
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
        
        # Add wind indicator
        wind_speed_kts = self.wind_data['surface']['speed_mps'] * 1.94384
        wind_dir = self.wind_data['surface']['direction']
        
        # Add a simple wind indicator near the map
        wind_html = f"""
        <div style="position: fixed; top: 10px; right: 10px; 
                    background: white; padding: 10px; border: 2px solid black;
                    border-radius: 5px; z-index: 1000;">
            <b>Surface Wind:</b><br>
            {wind_speed_kts:.0f} kts from {wind_dir}°
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
        
        # Add BKK Airport
        folium.Marker(
            [BKK_LAT, BKK_LON], 
            popup="Suvarnabhumi Airport (BKK)",
            icon=folium.Icon(color='red', icon='star')
        ).add_to(m)
        
        # Add title
        title_html = f"""
        <div style="position: fixed; top: 10px; left: 50%; transform: translateX(-50%);
                    background: #2c3e50; color: white; padding: 10px 20px;
                    border-radius: 5px; z-index: 1000;">
            <h3 style="margin: 0;">Bangkok Wind & Weather Flight Radar</h3>
            <p style="margin: 0; font-size: 12px;">{current_time.strftime('%Y-%m-%d %H:%M:%S')}</p>
        </div>
        """
        m.get_root().html.add_child(folium.Element(title_html))
        
        # Save map
        timestamp = current_time.strftime('%Y%m%d_%H%M%S')
        filename = f"wind_weather_map_{timestamp}.html"
        m.save(filename)
        
        print(f"\nMap saved as: {filename}")
        print(f"Total flights shown: {len(self.flight_data)}")
        
        # Print summary
        headwind_count = sum(1 for f in self.flight_data if 'HEADWIND' in f['wind_condition'])
        tailwind_count = sum(1 for f in self.flight_data if 'TAILWIND' in f['wind_condition'])
        
        print(f"\nWind Analysis Summary:")
        print(f"- Flights with headwind: {headwind_count}")
        print(f"- Flights with tailwind: {tailwind_count}")
        print(f"- Surface wind: {wind_speed_kts:.0f} kts from {wind_dir}°")
        
        return filename

    def run_single_analysis(self):
        """Run a single analysis"""
        print("\nFetching data...")
        
        # Get weather data
        self.get_weather_data()
        
        # Process flights
        self.process_flights()
        
        if self.flight_data:
            # Create map
            filename = self.create_map()
            print(f"\nOpen {filename} in your browser to view the map")
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
                
                self.get_weather_data()
                self.process_flights()
                
                if self.flight_data:
                    self.create_map()
                else:
                    print("No arrival flights found")
                
                print(f"\nNext update in {interval_minutes} minutes...")
                time.sleep(interval_minutes * 60)
                
        except KeyboardInterrupt:
            print(f"\nMonitoring stopped after {count} updates")

def main():
    print("\n=== SIMPLIFIED WIND & WEATHER FLIGHT RADAR ===")
    print("\nFeatures:")
    print("- Real-time flight tracking near Bangkok")
    print("- Wind analysis (headwind/tailwind)")
    print("- Weather radar overlay")
    print("- Color-coded flights by wind condition")
    
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