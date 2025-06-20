import requests
import folium
import datetime
import os
import time
import json
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from math import sin, cos, sqrt, atan2, radians

# Bangkok/BKK Airport coordinates
BANGKOK_CENTER_LAT, BANGKOK_CENTER_LON = 13.7563, 100.5018
BKK_LAT, BKK_LON = 13.6811, 100.7475

# Bangkok area bounds for flight tracking
BBOX = {
    "lamin": 13.1,   # South
    "lamax": 14.3,   # North  
    "lomin": 100.2,  # West
    "lomax": 101.3   # East
}

# Weather echo classification thresholds (simulated radar intensity)
ECHO_CLASSIFICATIONS = {
    "GREEN": {"min_dbz": 5, "max_dbz": 30, "action": "GO_THROUGH", "severity": 1},
    "YELLOW": {"min_dbz": 30, "max_dbz": 40, "action": "GO_THROUGH_CAUTION", "severity": 2},
    "ORANGE": {"min_dbz": 40, "max_dbz": 50, "action": "AVOID_CIRCUMNAVIGATE", "severity": 3},
    "RED": {"min_dbz": 50, "max_dbz": 60, "action": "MANDATORY_AVOIDANCE", "severity": 4},
    "MAGENTA": {"min_dbz": 60, "max_dbz": 100, "action": "COMPLETE_AVOIDANCE", "severity": 5}
}

class IntegratedFlightWeatherClassifier:
    def __init__(self):
        self.driver = None
        self.setup_driver()
        self.weather_data = None
        self.flight_data = []
        self.classifications = []
        
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
            print(f"⚠️ Chrome driver not available: {str(e)}")
            self.driver = None

    def get_radar_data(self):
        """Get latest radar frame data"""
        url = "https://api.rainviewer.com/public/weather-maps.json"
        try:
            response = requests.get(url, timeout=30)
            data = response.json()
            
            radar_frames = data.get("radar", {}).get("past", [])
            if radar_frames:
                latest_frame = radar_frames[-1]
                self.weather_data = {
                    'path': latest_frame['path'],
                    'time': latest_frame['time'],
                    'timestamp': datetime.datetime.fromtimestamp(latest_frame['time'])
                }
                print(f"📡 Retrieved radar data: {self.weather_data['timestamp']}")
                return True
            return False
        except Exception as e:
            print(f"❌ Error fetching radar data: {str(e)}")
            return False

    def get_flights_near_bkk(self):
        """Fetch flights within BKK area"""
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
        """
        Simulate radar echo intensity based on geographic patterns
        In real implementation, this would query actual radar data
        """
        # Simulate weather patterns around BKK
        distance_to_bkk = self.calculate_distance(lat, lon, BKK_LAT, BKK_LON)
        
        # Create simulated weather zones
        if 13.9 <= lat <= 14.2 and 100.6 <= lon <= 100.9:  # North approach
            return 45  # Orange zone
        elif 13.6 <= lat <= 13.8 and 101.0 <= lon <= 101.2:  # East sector
            return 55  # Red zone
        elif 13.3 <= lat <= 13.5 and 100.3 <= lon <= 100.6:  # Southwest
            return 25  # Green zone
        elif distance_to_bkk < 20:  # Near airport
            return 15  # Light precipitation
        else:
            return 0   # Clear

    def classify_echo_intensity(self, dbz_value):
        """Classify radar echo intensity into action categories"""
        for color, thresholds in ECHO_CLASSIFICATIONS.items():
            if thresholds["min_dbz"] <= dbz_value <= thresholds["max_dbz"]:
                return {
                    "color": color,
                    "dbz": dbz_value,
                    "action": thresholds["action"],
                    "severity": thresholds["severity"]
                }
        return {
            "color": "CLEAR",
            "dbz": dbz_value,
            "action": "GO_THROUGH",
            "severity": 0
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

    def estimate_arrival_time(self, flight):
        """Estimate arrival time based on distance and speed"""
        lat, lon, velocity = flight[6], flight[5], flight[9]
        
        if not all([lat, lon, velocity]) or velocity < 10:
            return None
        
        distance = self.calculate_distance(lat, lon, BKK_LAT, BKK_LON)
        velocity_kmh = velocity * 3.6
        time_minutes = (distance / velocity_kmh) * 60
        eta = datetime.datetime.now() + datetime.timedelta(minutes=time_minutes)
        
        return {
            "distance_km": distance,
            "eta": eta,
            "minutes_to_arrival": time_minutes
        }

    def classify_flight_weather_interaction(self, flight):
        """Main classification function for flight-weather interaction"""
        if not self.is_arrival_flight(flight):
            return None
        
        lat, lon = flight[6], flight[5]
        callsign = flight[1].strip() if flight[1] else "Unknown"
        altitude = flight[7]
        velocity = flight[9]
        
        # Get radar intensity at flight position
        radar_intensity = self.simulate_radar_intensity(lat, lon)
        echo_classification = self.classify_echo_intensity(radar_intensity)
        
        # Get arrival data
        eta_data = self.estimate_arrival_time(flight)
        if not eta_data:
            return None
        
        # Determine aircraft decision
        actual_decision = self.determine_aircraft_decision(flight, echo_classification)
        
        # Create classification record
        classification = {
            "timestamp": datetime.datetime.now(),
            "flight_id": callsign,
            "icao24": flight[0],
            "position": {"lat": lat, "lon": lon},
            "altitude_ft": int(altitude * 3.28084) if altitude else None,
            "speed_kts": int(velocity * 1.94384) if velocity else None,
            "distance_to_bkk": eta_data["distance_km"],
            "eta_minutes": eta_data["minutes_to_arrival"],
            "radar_echo": {
                "intensity_dbz": radar_intensity,
                "color": echo_classification["color"],
                "recommended_action": echo_classification["action"],
                "severity_level": echo_classification["severity"]
            },
            "aircraft_decision": actual_decision,
            "classification": self.get_final_classification(echo_classification["action"], actual_decision),
            "weather_impact": self.assess_weather_impact(echo_classification, actual_decision)
        }
        
        return classification

    def determine_aircraft_decision(self, flight, echo_classification):
        """
        Determine what the aircraft actually did based on flight parameters
        In real implementation, this would track actual flight path changes
        """
        severity = echo_classification["severity"]
        altitude = flight[7] if flight[7] else 0
        vertical_rate = flight[11] if flight[11] else 0
        
        # Simulate aircraft decision logic
        if severity >= 4:  # Red/Magenta echoes
            return "AVOIDED" if altitude > 1500 else "DIVERTED"
        elif severity == 3:  # Orange echoes
            return "CIRCUMNAVIGATED" if abs(vertical_rate) > 5 else "CONTINUED_WITH_CAUTION"
        else:  # Green/Yellow echoes
            return "CONTINUED_NORMAL"

    def get_final_classification(self, recommended_action, actual_decision):
        """Classify the case based on recommended vs actual action"""
        go_through_actions = ["CONTINUED_NORMAL", "CONTINUED_WITH_CAUTION"]
        avoid_actions = ["AVOIDED", "CIRCUMNAVIGATED", "DIVERTED"]
        
        if "GO_THROUGH" in recommended_action and actual_decision in go_through_actions:
            return "COMPLIANT_GO_THROUGH"
        elif "AVOID" in recommended_action and actual_decision in avoid_actions:
            return "COMPLIANT_AVOIDANCE"
        elif "GO_THROUGH" in recommended_action and actual_decision in avoid_actions:
            return "CONSERVATIVE_AVOIDANCE"
        elif "AVOID" in recommended_action and actual_decision in go_through_actions:
            return "RISKY_PENETRATION"
        else:
            return "UNDETERMINED"

    def assess_weather_impact(self, echo_classification, actual_decision):
        """Assess the impact of weather on flight operations"""
        severity = echo_classification["severity"]
        
        impact_levels = {
            0: "NO_IMPACT",
            1: "MINIMAL_IMPACT", 
            2: "MINOR_IMPACT",
            3: "MODERATE_IMPACT",
            4: "SIGNIFICANT_IMPACT",
            5: "SEVERE_IMPACT"
        }
        
        base_impact = impact_levels.get(severity, "UNKNOWN")
        
        # Adjust based on actual decision
        if actual_decision in ["DIVERTED", "AVOIDED"]:
            return f"{base_impact}_WITH_OPERATIONAL_DISRUPTION"
        else:
            return base_impact

    def process_all_flights(self):
        """Process all flights and create classifications"""
        flights = self.get_flights_near_bkk()
        if not flights:
            return []
        
        self.classifications = []
        arrivals_processed = 0
        
        for flight in flights:
            if not flight or len(flight) < 12:
                continue
                
            classification = self.classify_flight_weather_interaction(flight)
            if classification:
                self.classifications.append(classification)
                arrivals_processed += 1
        
        print(f"📊 Processed {arrivals_processed} arrival flights")
        return self.classifications

    def save_classification_data(self):
        """Save classification data to files"""
        if not self.classifications:
            print("⚠️ No classification data to save")
            return
        
        # Create output directory
        output_dir = "flight_weather_classifications"
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        # Create filename with timestamp
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        json_file = os.path.join(output_dir, f"classifications_{timestamp}.json")
        summary_file = os.path.join(output_dir, f"summary_{timestamp}.txt")
        
        # Save detailed JSON data
        with open(json_file, 'w') as f:
            json.dump(self.classifications, f, indent=2, default=str)
        
        # Create summary report
        self.create_summary_report(summary_file)
        
        print(f"💾 Saved classification data:")
        print(f"   📄 Detailed: {json_file}")
        print(f"   📋 Summary: {summary_file}")

    def create_summary_report(self, filename):
        """Create a human-readable summary report"""
        if not self.classifications:
            return
        
        # Calculate statistics
        total_flights = len(self.classifications)
        classification_counts = {}
        weather_impacts = {}
        echo_colors = {}
        
        for record in self.classifications:
            # Count final classifications
            final_class = record["classification"]
            classification_counts[final_class] = classification_counts.get(final_class, 0) + 1
            
            # Count weather impacts
            impact = record["weather_impact"]
            weather_impacts[impact] = weather_impacts.get(impact, 0) + 1
            
            # Count echo colors
            color = record["radar_echo"]["color"]
            echo_colors[color] = echo_colors.get(color, 0) + 1
        
        # Write summary report
        with open(filename, 'w') as f:
            f.write("FLIGHT WEATHER ECHO CLASSIFICATION REPORT\n")
            f.write("=" * 50 + "\n\n")
            
            f.write(f"Report Generated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Total Flights Analyzed: {total_flights}\n\n")
            
            # Classification breakdown
            f.write("CLASSIFICATION BREAKDOWN:\n")
            f.write("-" * 30 + "\n")
            for class_type, count in sorted(classification_counts.items()):
                percentage = (count / total_flights) * 100
                f.write(f"{class_type}: {count} ({percentage:.1f}%)\n")
            
            f.write("\nWEATHER ECHO INTENSITY:\n")
            f.write("-" * 30 + "\n")
            for color, count in sorted(echo_colors.items()):
                percentage = (count / total_flights) * 100
                f.write(f"{color}: {count} ({percentage:.1f}%)\n")
            
            f.write("\nWEATHER IMPACT LEVELS:\n")
            f.write("-" * 30 + "\n")
            for impact, count in sorted(weather_impacts.items()):
                percentage = (count / total_flights) * 100
                f.write(f"{impact}: {count} ({percentage:.1f}%)\n")
            
            # Safety analysis
            risky_penetrations = classification_counts.get("RISKY_PENETRATION", 0)
            f.write(f"\nSAFETY ANALYSIS:\n")
            f.write("-" * 30 + "\n")
            f.write(f"Risky Weather Penetrations: {risky_penetrations}\n")
            f.write(f"Safety Compliance Rate: {((total_flights - risky_penetrations) / total_flights * 100):.1f}%\n")
            
            # Detailed records
            f.write(f"\nDETAILED FLIGHT RECORDS:\n")
            f.write("-" * 30 + "\n")
            for i, record in enumerate(self.classifications, 1):
                f.write(f"\n{i}. Flight {record['flight_id']}:\n")
                f.write(f"   Position: {record['position']['lat']:.3f}°N, {record['position']['lon']:.3f}°E\n")
                f.write(f"   Altitude: {record['altitude_ft']} ft\n")
                f.write(f"   Distance to BKK: {record['distance_to_bkk']:.1f} km\n")
                f.write(f"   Echo: {record['radar_echo']['color']} ({record['radar_echo']['intensity_dbz']} dBZ)\n")
                f.write(f"   Recommended: {record['radar_echo']['recommended_action']}\n")
                f.write(f"   Actual Decision: {record['aircraft_decision']}\n")
                f.write(f"   Classification: {record['classification']}\n")
                f.write(f"   Weather Impact: {record['weather_impact']}\n")

    def display_live_results(self):
        """Display real-time classification results"""
        if not self.classifications:
            print("📊 No classification data available")
            return
        
        print("\n" + "="*80)
        print("🛩️ LIVE FLIGHT WEATHER ECHO CLASSIFICATION RESULTS")
        print("="*80)
        
        # Sort by severity level (highest first)
        sorted_classifications = sorted(
            self.classifications, 
            key=lambda x: x["radar_echo"]["severity_level"], 
            reverse=True
        )
        
        for i, record in enumerate(sorted_classifications, 1):
            echo = record["radar_echo"]
            status_icon = self.get_status_icon(record["classification"])
            
            print(f"\n{i}. {status_icon} {record['flight_id']} | {echo['color']} ECHO ({echo['intensity_dbz']} dBZ)")
            print(f"   📍 Position: {record['position']['lat']:.3f}°N, {record['position']['lon']:.3f}°E")
            print(f"   ✈️ Alt: {record['altitude_ft']} ft | Spd: {record['speed_kts']} kts")
            print(f"   🎯 Distance to BKK: {record['distance_to_bkk']:.1f} km | ETA: {record['eta_minutes']:.0f} min")
            print(f"   🌦️ Recommended: {echo['recommended_action']}")
            print(f"   ✅ Aircraft Action: {record['aircraft_decision']}")
            print(f"   📊 Classification: {record['classification']}")
            print(f"   ⚡ Impact: {record['weather_impact']}")

    def get_status_icon(self, classification):
        """Get status icon based on classification"""
        icons = {
            "COMPLIANT_GO_THROUGH": "✅",
            "COMPLIANT_AVOIDANCE": "✅", 
            "CONSERVATIVE_AVOIDANCE": "⚠️",
            "RISKY_PENETRATION": "🚨",
            "UNDETERMINED": "❓"
        }
        return icons.get(classification, "❓")

    def run_continuous_monitoring(self, interval_minutes=5):
        """Run continuous monitoring and classification"""
        print(f"🔄 Starting continuous flight weather classification")
        print(f"⏱️ Collection interval: {interval_minutes} minutes")
        print(f"🎯 Focus area: Bangkok & BKK Airport")
        print(f"🛑 Press Ctrl+C to stop\n")
        
        collection_count = 0
        
        try:
            while True:
                collection_count += 1
                current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                print(f"\n🕐 [{current_time}] Collection #{collection_count}")
                print("-" * 50)
                
                # Get radar data
                radar_success = self.get_radar_data()
                
                # Process flights
                if radar_success:
                    classifications = self.process_all_flights()
                    
                    if classifications:
                        # Display results
                        self.display_live_results()
                        
                        # Save data
                        self.save_classification_data()
                        
                        # Quick statistics
                        total = len(classifications)
                        risky = sum(1 for c in classifications if c["classification"] == "RISKY_PENETRATION")
                        print(f"\n📈 Quick Stats: {total} flights analyzed, {risky} risky penetrations")
                    else:
                        print("📊 No arrival flights to classify")
                else:
                    print("❌ Failed to get radar data")
                
                # Wait for next collection
                next_time = datetime.datetime.now() + datetime.timedelta(minutes=interval_minutes)
                print(f"\n⏰ Next collection at: {next_time.strftime('%H:%M:%S')}")
                time.sleep(interval_minutes * 60)
                
        except KeyboardInterrupt:
            print(f"\n🛑 Monitoring stopped by user after {collection_count} collections")
        finally:
            if self.driver:
                self.driver.quit()

    def run_single_analysis(self):
        """Run a single analysis cycle"""
        print("🛩️ FLIGHT WEATHER ECHO CLASSIFICATION - SINGLE ANALYSIS")
        print("="*60)
        
        # Get radar data
        print("📡 Fetching weather radar data...")
        if not self.get_radar_data():
            print("❌ Failed to get radar data. Exiting.")
            return
        
        # Process flights
        print("✈️ Processing flight data...")
        classifications = self.process_all_flights()
        
        if not classifications:
            print("📊 No arrival flights found for classification")
            return
        
        # Display and save results
        self.display_live_results()
        self.save_classification_data()
        
        # Final summary
        total = len(classifications)
        go_through = sum(1 for c in classifications if "GO_THROUGH" in c["classification"])
        avoid = sum(1 for c in classifications if "AVOIDANCE" in c["classification"])
        risky = sum(1 for c in classifications if c["classification"] == "RISKY_PENETRATION")
        
        print(f"\n📊 FINAL SUMMARY:")
        print(f"   Total flights analyzed: {total}")
        print(f"   Go through weather: {go_through} ({go_through/total*100:.1f}%)")
        print(f"   Avoid weather: {avoid} ({avoid/total*100:.1f}%)")
        print(f"   Risky penetrations: {risky} ({risky/total*100:.1f}%)")

def main():
    print("\n" + "="*70)
    print("🛩️ INTEGRATED FLIGHT WEATHER ECHO CLASSIFICATION SYSTEM")
    print("="*70)
    print("🎯 Purpose: Classify how aircraft interact with weather echoes")
    print("📡 Data Sources: RainViewer radar + OpenSky flight tracking")
    print("🌍 Coverage: Bangkok & BKK Airport region")
    print("\n📋 Options:")
    print("   1. Single analysis (one-time classification)")
    print("   2. Continuous monitoring (real-time classification)")
    
    choice = input("\n🎯 Enter your choice (1 or 2): ")
    
    classifier = IntegratedFlightWeatherClassifier()
    
    if choice == "1":
        classifier.run_single_analysis()
    elif choice == "2":
        try:
            interval = input("⏱️ Enter monitoring interval in minutes (default: 5): ")
            interval = int(interval) if interval.strip() else 5
            if interval < 2:
                print("⚠️ Minimum interval is 2 minutes. Setting to 2.")
                interval = 2
            classifier.run_continuous_monitoring(interval)
        except ValueError:
            print("❌ Invalid input. Using default (5 minutes).")
            classifier.run_continuous_monitoring(5)
    else:
        print("❌ Invalid choice. Exiting.")

if __name__ == "__main__":
    main()