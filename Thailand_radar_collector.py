import requests
import folium
import datetime
import os
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from PIL import Image
import io
import base64

# Bangkok/BKK Airport focused coordinates and bounds
BANGKOK_CENTER_LAT, BANGKOK_CENTER_LON = 13.7563, 100.5018  # Bangkok center
BKK_LAT, BKK_LON = 13.690, 100.750  # BKK Airport

# Bangkok metropolitan area bounds (focused on airport region)
BANGKOK_BOUNDS = {
    'north': 14.2,   # North of Bangkok
    'south': 13.2,   # South of Bangkok  
    'east': 101.2,   # East of Bangkok
    'west': 100.0    # West of Bangkok
}

class BangkokRadarCollector:
    def __init__(self):
        self.driver = None
        self.setup_driver()
    
    def setup_driver(self):
        """Setup Chrome driver for screenshot capture"""
        try:
            chrome_options = Options()
            chrome_options.add_argument('--headless')  # Run in background
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--window-size=1920,1080')
            chrome_options.add_argument('--disable-gpu')
            
            self.driver = webdriver.Chrome(options=chrome_options)
            print("✅ Chrome driver initialized successfully")
        except Exception as e:
            print(f"❌ Error setting up Chrome driver: {str(e)}")
            print("Please install ChromeDriver: https://chromedriver.chromium.org/")
            self.driver = None
    
    def get_recent_radar_frames(self, hours_ago=2):
        """Get all available radar frames from the past hours"""
        url = "https://api.rainviewer.com/public/weather-maps.json"
        try:
            response = requests.get(url, timeout=30)
            data = response.json()
            
            all_frames = data.get("radar", {}).get("past", [])
            
            now = datetime.datetime.now()
            start_time = int((now - datetime.timedelta(hours=hours_ago)).timestamp())
            
            recent_frames = [frame for frame in all_frames if frame['time'] >= start_time]
            
            print(f"📡 Found {len(recent_frames)} radar frames from the past {hours_ago} hours")
            return recent_frames
        except Exception as e:
            print(f"❌ Error fetching radar data: {str(e)}")
            return []

    def get_latest_radar_frame(self):
        """Get latest radar frame only"""
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

    def create_bangkok_radar_map(self, frame, save_images=True):
        """Create radar map focused on Bangkok/BKK Airport area and save as static files"""
        path = frame['path']
        timestamp = frame['time']
        
        # Convert Unix timestamp to datetime
        radar_time = datetime.datetime.fromtimestamp(timestamp)
        formatted_time = radar_time.strftime("%Y-%m-%d %H:%M:%S")
        
        # Create base folder for Bangkok radar data
        base_folder = "bangkok_radar_data"
        if not os.path.exists(base_folder):
            os.makedirs(base_folder)
        
        # Create subfolder with today's date
        date_folder = os.path.join(base_folder, radar_time.strftime("%Y%m%d"))
        if not os.path.exists(date_folder):
            os.makedirs(date_folder)
        
        # Create filenames with timestamp (PNG only)
        time_str = radar_time.strftime('%H%M%S')
        html_file = os.path.join(date_folder, f"bangkok_radar_{time_str}.html")
        png_file = os.path.join(date_folder, f"bangkok_radar_{time_str}.png")
        summary_file = os.path.join(date_folder, f"bangkok_radar_{time_str}_data.txt")
        
        # Check if files already exist
        if os.path.exists(png_file) and os.path.exists(html_file):
            print(f"📁 Files already exist for {formatted_time}")
            return True
        
        try:
            # Create map focused on Bangkok/BKK Airport area
            m = folium.Map(
                location=[BANGKOK_CENTER_LAT, BANGKOK_CENTER_LON], 
                zoom_start=10,  # Higher zoom for Bangkok detail
                tiles='OpenStreetMap',
                width='100%',
                height='100%'
            )
            
            # Add weather radar overlay with higher opacity for better visibility
            radar_layer = folium.raster_layers.TileLayer(
                tiles=f"https://tilecache.rainviewer.com{path}/256/{{z}}/{{x}}/{{y}}/2/1_1.png",
                attr="RainViewer | Thailand Weather Data",
                name="Weather Radar",
                overlay=True,
                control=True,
                opacity=0.8  # Higher opacity for better screenshots
            )
            radar_layer.add_to(m)
            
            # Add BKK Airport marker
            folium.Marker(
                [BKK_LAT, BKK_LON], 
                tooltip="BKK Airport",
                popup="Suvarnabhumi Airport (BKK)",
                icon=folium.Icon(color='red', icon='plane', prefix='fa')
            ).add_to(m)
            
            # Add Bangkok area locations with better visibility
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
            
            # Set map bounds to Bangkok area
            m.fit_bounds([
                [BANGKOK_BOUNDS['south'], BANGKOK_BOUNDS['west']],
                [BANGKOK_BOUNDS['north'], BANGKOK_BOUNDS['east']]
            ])
            
            # Add comprehensive title and info for Bangkok
            title_html = f'''
                <div style="position: fixed; 
                            top: 15px; 
                            left: 50%; 
                            transform: translateX(-50%);
                            width: 500px; 
                            height: 80px; 
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
                    ✈️ Bangkok & BKK Airport Weather Radar<br>
                    <span style="font-size: 14px; font-weight: normal;">📅 {formatted_time}</span><br>
                    <span style="font-size: 12px; font-weight: normal;">🛰️ High Detail • 📍 Bangkok Metro Area</span>
                </div>
            '''
            m.get_root().html.add_child(folium.Element(title_html))
            
            # Add CSS for better screenshot quality
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
            
            # Save HTML file first
            m.save(html_file)
            print(f"💾 Saved HTML: {os.path.basename(html_file)}")
            
            # Take screenshot if driver is available (PNG only)
            if save_images and self.driver:
                self.capture_screenshot_png(html_file, png_file, formatted_time)
            
            # Create detailed summary file
            with open(summary_file, 'w', encoding='utf-8') as f:
                f.write(f"✈️ BANGKOK & BKK AIRPORT WEATHER RADAR DATA\n")
                f.write(f"=" * 50 + "\n\n")
                f.write(f"📅 Collection Time: {formatted_time}\n")
                f.write(f"🛰️ Data Source: RainViewer API\n")
                f.write(f"🗺️ Geographic Focus: Bangkok Metropolitan Area\n")
                f.write(f"📍 Map Center: {BANGKOK_CENTER_LAT}°N, {BANGKOK_CENTER_LON}°E\n")
                f.write(f"✈️ BKK Airport: {BKK_LAT}°N, {BKK_LON}°E\n")
                f.write(f"🔍 Zoom Level: 10 (High Detail)\n")
                f.write(f"🔗 Radar API Path: {path}\n")
                f.write(f"📁 HTML File: {os.path.basename(html_file)}\n")
                f.write(f"🖼️ PNG File: {os.path.basename(png_file)}\n\n")
                f.write(f"BANGKOK COVERAGE BOUNDS:\n")
                f.write(f"🧭 North: {BANGKOK_BOUNDS['north']}°N\n")
                f.write(f"🧭 South: {BANGKOK_BOUNDS['south']}°N\n")
                f.write(f"🧭 East: {BANGKOK_BOUNDS['east']}°E\n")
                f.write(f"🧭 West: {BANGKOK_BOUNDS['west']}°E\n\n")
                f.write(f"KEY LOCATIONS INCLUDED:\n")
                for location in bangkok_locations:
                    f.write(f"📍 {location['name']}: {location['lat']}°N, {location['lon']}°E\n")
            
            print(f"✅ Bangkok radar data saved: {formatted_time}")
            return True
            
        except Exception as e:
            print(f"❌ Error creating Bangkok radar map: {str(e)}")
            return False

    def capture_screenshot_png(self, html_file, png_file, formatted_time):
        """Capture PNG screenshot of the Bangkok map"""
        try:
            # Load the HTML file
            file_url = f"file://{os.path.abspath(html_file)}"
            self.driver.get(file_url)
            
            # Wait for map to load
            print(f"📸 Taking Bangkok screenshot for {formatted_time}...")
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CLASS_NAME, "leaflet-container"))
            )
            
            # Additional wait for tiles to load (longer for detailed view)
            time.sleep(5)
            
            # Take screenshot as PNG with high resolution
            self.driver.set_window_size(1920, 1080)  # Set high resolution
            self.driver.save_screenshot(png_file)
            print(f"🖼️ Saved Bangkok PNG: {os.path.basename(png_file)}")
                
        except Exception as e:
            print(f"❌ Error capturing Bangkok screenshot: {str(e)}")

    def create_latest_bangkok_radar(self):
        """Create radar map for latest frame (Bangkok focus)"""
        path, timestamp = self.get_latest_radar_frame()
        if not path or not timestamp:
            print("❌ No radar data available.")
            return False
        
        frame = {'path': path, 'time': timestamp}
        return self.create_bangkok_radar_map(frame)

    def collect_recent_bangkok_data(self):
        """Collect Bangkok radar data from the past 2 hours"""
        print("✈️ Retrieving Bangkok & BKK Airport radar data from the past 2 hours...")
        frames = self.get_recent_radar_frames(hours_ago=2)
        
        if not frames:
            print("❌ No radar data available for the specified time period.")
            return
        
        total_frames = len(frames)
        print(f"🔄 Processing {total_frames} radar frames for Bangkok area...")
        
        success_count = 0
        for i, frame in enumerate(frames):
            print(f"⏳ Processing Bangkok frame {i+1}/{total_frames}...")
            success = self.create_bangkok_radar_map(frame)
            if success:
                success_count += 1
            
            # Small delay to avoid overwhelming the server
            time.sleep(1)
        
        print(f"✅ Successfully saved {success_count} out of {total_frames} Bangkok radar maps.")

    def run_continuous_bangkok_collection(self, interval_minutes=10):
        """Run continuous Bangkok radar collection"""
        print(f"🔄 Starting Bangkok radar collection every {interval_minutes} minutes.")
        print(f"🎯 Focus: Bangkok & BKK Airport ({BANGKOK_CENTER_LAT}°N, {BANGKOK_CENTER_LON}°E)")
        print(f"💾 Data saved as: HTML + PNG + Summary")
        print(f"🛑 Press Ctrl+C to stop. Data will be saved to 'bangkok_radar_data' folder.")
        
        collection_count = 0
        
        try:
            while True:
                current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                collection_count += 1
                
                print(f"\n🕐 [{current_time}] Collection #{collection_count}: Fetching Bangkok radar data...")
                
                success = self.create_latest_bangkok_radar()
                if success:
                    print(f"✅ Bangkok collection #{collection_count} successful.")
                else:
                    print(f"❌ Bangkok collection #{collection_count} failed.")
                
                next_time = datetime.datetime.now() + datetime.timedelta(minutes=interval_minutes)
                print(f"⏰ Next Bangkok collection at: {next_time.strftime('%H:%M:%S')}")
                print("🌦️ Monitoring Bangkok weather... (keep this window open)")
                
                time.sleep(interval_minutes * 60)
                
        except KeyboardInterrupt:
            print(f"\n🛑 Bangkok radar collection stopped by user.")
            print(f"📊 Completed {collection_count} collections.")
        finally:
            if self.driver:
                self.driver.quit()

    def __del__(self):
        """Cleanup driver when object is destroyed"""
        if self.driver:
            self.driver.quit()

def main():
    print("\n" + "="*60)
    print("🇹🇭 THAILAND WEATHER RADAR COLLECTION TOOL")
    print("="*60)
    print("✨ Features:")
    print("   📊 Focused on Thailand region for optimal performance")
    print("   💾 Saves HTML + PNG + JPG + Summary files")
    print("   🛡️ Prevents data loss with static image capture")
    print("   ✈️ Includes BKK Airport and major Thai cities")
    print("   🔄 Continuous monitoring every 10 minutes")
    print("\n📋 Options:")
    print("   1. Collect Thailand radar data from past 2 hours (one-time)")
    print("   2. Run continuous Thailand collection")
    
    choice = input("\n🎯 Enter your choice (1 or 2): ")
    
    collector = BangkokRadarCollector()
    
    if not collector.driver:
        print("\n⚠️ WARNING: Screenshot capture disabled (Chrome driver not available)")
        print("   HTML files will still be saved, but no PNG images")
        proceed = input("   Continue anyway? (y/n): ")
        if proceed.lower() != 'y':
            return
    
    if choice == "1":
        collector.collect_recent_bangkok_data()
    
    elif choice == "2":
        try:
            interval = input("⏱️ Enter collection interval in minutes (default: 10): ")
            interval = int(interval) if interval.strip() else 10
            if interval < 5:
                print("⚠️ Minimum interval is 5 minutes to avoid server overload.")
                interval = 5
            collector.run_continuous_bangkok_collection(interval)
        except ValueError:
            print("❌ Invalid input. Using default (10 minutes).")
            collector.run_continuous_bangkok_collection(10)
    
    else:
        print("❌ Invalid choice. Exiting.")

if __name__ == "__main__":
    main()