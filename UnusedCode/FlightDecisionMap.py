#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Thailand Map with Flight Weather Radar Integration
Combines Thailand outline map with real-time flight weather classifications
"""

import matplotlib.pyplot as plt
import matplotlib.patches as patches
import numpy as np
import requests
import datetime
import json
from math import sin, cos, sqrt, atan2, radians
import time

# BKK Airport coordinates
BKK_LAT, BKK_LON = 13.6811, 100.7475
BANGKOK_CENTER_LAT, BANGKOK_CENTER_LON = 13.7563, 100.5018

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

class ThailandFlightRadarMap:
    def __init__(self, thailand_map_path):
        self.thailand_map_path = thailand_map_path
        self.thailand_segments = []
        self.flight_data = []
        self.weather_zones = []
        
    def load_thailand_map(self):
        """Load Thailand outline from CSV file"""
        print("📍 Loading Thailand map outline...")
        
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
            print("📝 Creating simulated Thailand outline...")
            # Create simplified Thailand outline if file not found
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
        # Simplified Thailand border coordinates
        thailand_outline = [
            # Main Thailand outline (simplified)
            ([97.5, 98.5, 99.5, 100.5, 101.5, 102.5, 103.5, 104.5, 105.0, 104.5, 104.0, 103.0, 102.0, 101.0, 100.0, 99.0, 98.5, 98.0, 97.5, 97.5],
             [20.0, 19.5, 19.0, 18.5, 17.5, 16.0, 14.5, 13.0, 12.0, 11.0, 10.5, 9.5, 8.5, 8.0, 7.5, 8.0, 9.0, 12.0, 15.0, 20.0]),
            # Bangkok area detail
            ([100.0, 100.8, 100.8, 100.0, 100.0],
             [13.2, 13.2, 14.2, 14.2, 13.2])
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

    def plot_integrated_map(self, save_file=None):
        """Create integrated Thailand map with flight radar overlay"""
        # Set up the plot
        plt.figure(figsize=(14, 12))
        plt.gca().set_aspect('equal')
        
        # Plot Thailand outline
        print("🗺️ Drawing Thailand map...")
        for i, (lon_seg, lat_seg) in enumerate(self.thailand_segments):
            plt.plot(lon_seg, lat_seg, color='black', linewidth=1.5, alpha=0.8)

        # Set map bounds (focus on Bangkok area but show Thailand context)
        plt.xlim(95, 110)
        plt.ylim(5, 25)
        
        # Add weather zones
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
                linewidth=1,
                edgecolor='gray',
                facecolor=echo_props["color"],
                alpha=echo_props["alpha"],
                label=f'{zone["name"]} ({echo_color})'
            )
            plt.gca().add_patch(rect)

        # Plot flight data
        print("✈️ Adding flight positions...")
        classification_colors = {
            "COMPLIANT_GO_THROUGH": "green",
            "COMPLIANT_AVOIDANCE": "blue", 
            "RISKY_PENETRATION": "red",
            "CONSERVATIVE_AVOIDANCE": "orange"
        }
        
        for flight in self.flight_data:
            color = classification_colors.get(flight["classification"], "gray")
            
            # Plot flight position
            plt.scatter(flight["lon"], flight["lat"], 
                       c=color, s=100, marker='^', 
                       edgecolors='black', linewidth=1,
                       alpha=0.9, zorder=5)
            
            # Add flight label
            plt.annotate(f'{flight["callsign"]}\n{flight["altitude_ft"]}ft', 
                        (flight["lon"], flight["lat"]),
                        xytext=(5, 5), textcoords='offset points',
                        fontsize=8, fontweight='bold',
                        bbox=dict(boxstyle="round,pad=0.3", facecolor=color, alpha=0.7))

        # Add BKK Airport marker
        plt.scatter(BKK_LON, BKK_LAT, c='red', s=200, marker='s', 
                   edgecolors='black', linewidth=2, zorder=10,
                   label='BKK Airport')
        plt.annotate('BKK Airport', (BKK_LON, BKK_LAT),
                    xytext=(10, 10), textcoords='offset points',
                    fontsize=10, fontweight='bold',
                    bbox=dict(boxstyle="round,pad=0.5", facecolor='white', alpha=0.9))

        # Add Bangkok center
        plt.scatter(BANGKOK_CENTER_LON, BANGKOK_CENTER_LAT, c='blue', s=100, 
                   marker='o', edgecolors='black', linewidth=1, zorder=10,
                   label='Bangkok Center')

        # Create detailed inset for Bangkok area
        # Add inset axis
        from mpl_toolkits.axes_grid1.inset_locator import inset_axes
        axins = inset_axes(plt.gca(), width="30%", height="30%", loc='upper right')
        
        # Plot Bangkok detail in inset
        bangkok_bounds = [99.8, 101.5, 13.0, 14.5]
        axins.set_xlim(bangkok_bounds[0], bangkok_bounds[1])
        axins.set_ylim(bangkok_bounds[2], bangkok_bounds[3])
        
        # Thailand outline in inset
        for lon_seg, lat_seg in self.thailand_segments:
            axins.plot(lon_seg, lat_seg, color='black', linewidth=1, alpha=0.6)
        
        # Weather zones in inset
        for zone in self.weather_zones:
            bounds = zone["bounds"]
            intensity = zone["intensity"]
            echo_color, echo_props = self.classify_echo_intensity(intensity)
            
            rect = patches.Rectangle(
                (bounds[0], bounds[2]), bounds[1] - bounds[0], bounds[3] - bounds[2],
                linewidth=1, edgecolor='gray', facecolor=echo_props["color"],
                alpha=echo_props["alpha"]
            )
            axins.add_patch(rect)
        
        # Flights in inset
        for flight in self.flight_data:
            color = classification_colors.get(flight["classification"], "gray")
            axins.scatter(flight["lon"], flight["lat"], c=color, s=50, marker='^', 
                         edgecolors='black', linewidth=0.5, alpha=0.9)
        
        # BKK in inset
        axins.scatter(BKK_LON, BKK_LAT, c='red', s=100, marker='s', 
                     edgecolors='black', linewidth=1)
        
        axins.set_title('Bangkok Detail', fontsize=10)
        axins.grid(True, alpha=0.3)

        # Formatting
        plt.title(f'Thailand Flight Weather Radar\n{datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}', 
                 fontsize=16, fontweight='bold')
        plt.xlabel('Longitude', fontsize=12)
        plt.ylabel('Latitude', fontsize=12)
        plt.grid(True, alpha=0.3)
        plt.tick_params(labelsize=10)

        # Create custom legend
        legend_elements = [
            plt.Line2D([0], [0], marker='^', color='w', markerfacecolor='green', 
                      markersize=10, label='Safe Go-Through'),
            plt.Line2D([0], [0], marker='^', color='w', markerfacecolor='red', 
                      markersize=10, label='Risky Penetration'),
            plt.Line2D([0], [0], marker='^', color='w', markerfacecolor='blue', 
                      markersize=10, label='Compliant Avoidance'),
            plt.Line2D([0], [0], marker='s', color='w', markerfacecolor='red', 
                      markersize=10, label='BKK Airport'),
            plt.Rectangle((0,0), 1, 1, facecolor='green', alpha=0.3, label='Light Weather (Green)'),
            plt.Rectangle((0,0), 1, 1, facecolor='orange', alpha=0.5, label='Heavy Weather (Orange)'),
            plt.Rectangle((0,0), 1, 1, facecolor='red', alpha=0.6, label='Severe Weather (Red)')
        ]
        
        plt.legend(handles=legend_elements, loc='upper left', fontsize=10)

        # Add statistics box
        if self.flight_data:
            total_flights = len(self.flight_data)
            risky_flights = sum(1 for f in self.flight_data if f["classification"] == "RISKY_PENETRATION")
            safe_flights = total_flights - risky_flights
            
            stats_text = f"""Flight Statistics:
Total Arrivals: {total_flights}
Safe Operations: {safe_flights}
Risky Penetrations: {risky_flights}
Safety Rate: {(safe_flights/total_flights*100):.1f}%"""
            
            plt.text(0.02, 0.02, stats_text, transform=plt.gca().transAxes,
                    fontsize=10, verticalalignment='bottom',
                    bbox=dict(boxstyle="round,pad=0.5", facecolor='lightblue', alpha=0.8))

        plt.tight_layout()
        
        # Save if requested
        if save_file:
            plt.savefig(save_file, dpi=300, bbox_inches='tight')
            print(f"💾 Map saved as: {save_file}")
        
        plt.show()

        # Print summary
        self.print_flight_summary()

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

    def run_live_monitoring(self, interval_minutes=5, map_path=None):
        """Run continuous monitoring with map updates"""
        print(f"🔄 Starting live Thailand flight radar monitoring")
        print(f"⏱️ Update interval: {interval_minutes} minutes")
        print(f"🗺️ Map source: {self.thailand_map_path}")
        
        collection_count = 0
        
        try:
            while True:
                collection_count += 1
                current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                print(f"\n🕐 [{current_time}] Update #{collection_count}")
                print("-" * 50)
                
                # Process flight data
                self.create_weather_zones()
                flights = self.process_flight_data()
                
                if flights:
                    # Create map with timestamp
                    save_file = f"thailand_radar_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.png" if map_path else None
                    self.plot_integrated_map(save_file)
                else:
                    print("📊 No arrival flights detected")
                
                # Wait for next update
                next_time = datetime.datetime.now() + datetime.timedelta(minutes=interval_minutes)
                print(f"\n⏰ Next update at: {next_time.strftime('%H:%M:%S')}")
                time.sleep(interval_minutes * 60)
                
        except KeyboardInterrupt:
            print(f"\n🛑 Monitoring stopped after {collection_count} updates")

def main():
    print("\n" + "="*70)
    print("🇹🇭 THAILAND FLIGHT WEATHER RADAR MAP")
    print("="*70)
    
    # Get map file path
    map_path = input("📁 Enter path to thailand_outline.csv (or press Enter to use default): ").strip()
    if not map_path:
        map_path = "C:/Users/krith/Desktop/ATMCODE/Map/VTBS・BKK/thailand_outline.csv"
    
    # Create radar map system
    radar_map = ThailandFlightRadarMap(map_path)
    
    # Load Thailand map
    if not radar_map.load_thailand_map():
        print("❌ Failed to load Thailand map")
        return
    
    print("\n📋 Options:")
    print("   1. Single map with current flights")
    print("   2. Live monitoring with map updates")
    
    choice = input("\n🎯 Enter your choice (1 or 2): ")
    
    if choice == "1":
        print("🗺️ Creating single flight radar map...")
        radar_map.create_weather_zones()
        radar_map.process_flight_data()
        radar_map.plot_integrated_map("thailand_flight_radar.png")
        
    elif choice == "2":
        try:
            interval = input("⏱️ Enter update interval in minutes (default: 5): ")
            interval = int(interval) if interval.strip() else 5
            radar_map.run_live_monitoring(interval, "thailand_radar_maps")
        except ValueError:
            print("❌ Invalid input. Using default (5 minutes).")
            radar_map.run_live_monitoring(5, "thailand_radar_maps")
    else:
        print("❌ Invalid choice. Creating single map...")
        radar_map.create_weather_zones()
        radar_map.process_flight_data()
        radar_map.plot_integrated_map("thailand_flight_radar.png")

if __name__ == "__main__":
    main()