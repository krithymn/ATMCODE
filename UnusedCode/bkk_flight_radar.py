import requests
import datetime
from math import sin, cos, sqrt, atan2, radians

# BKK/VTBS airport coordinates
BKK_LAT = 13.6811
BKK_LON = 100.7475

# Bounding box around BKK (approximately 80km radius)
BBOX = {
    "lamin": 13.1,   # South
    "lamax": 14.3,   # North
    "lomin": 100.2,  # West
    "lomax": 101.3   # East
}

# Simplified radar echo zones (areas with precipitation)
ECHO_ZONES = [
    # Zone 1: North approach
    {
        "name": "North Approach Echo",
        "coords": [(100.6, 14.0), (100.9, 14.0), (100.9, 14.2), (100.6, 14.2)]
    },
    # Zone 2: East of airport
    {
        "name": "Eastern Sector Echo",
        "coords": [(101.0, 13.6), (101.2, 13.6), (101.2, 13.8), (101.0, 13.8)]
    }
]

def get_flights_near_bkk():
    """Fetch flights within the defined bounding box using OpenSky API"""
    url = "https://opensky-network.org/api/states/all"
    response = requests.get(url, params=BBOX)

    if response.status_code == 200:
        data = response.json()
        flights = data.get("states", [])
        print(f"Found {len(flights)} flights in the BKK/VTBS region\n")
        return flights
    else:
        print(f"Failed to fetch flight data: {response.status_code}")
        return []

def calculate_distance(lat1, lon1, lat2, lon2):
    """Calculate distance between two points in kilometers"""
    # Approximate radius of earth in km
    R = 6371.0

    lat1 = radians(lat1)
    lon1 = radians(lon1)
    lat2 = radians(lat2)
    lon2 = radians(lon2)

    dlon = lon2 - lon1
    dlat = lat2 - lat1

    a = sin(dlat / 2)**2 + cos(lat1) * cos(lat2) * sin(dlon / 2)**2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))

    distance = R * c
    return distance

def is_in_echo_zone(lat, lon):
    """Check if a point is in any echo zone"""
    if lat is None or lon is None:
        return False, None
        
    for zone in ECHO_ZONES:
        coords = zone["coords"]
        inside = False
        j = len(coords) - 1
        for i in range(len(coords)):
            if ((coords[i][1] > lat) != (coords[j][1] > lat)) and \
               (lon < coords[i][0] + (coords[j][0] - coords[i][0]) * (lat - coords[i][1]) / (coords[j][1] - coords[i][1])):
                inside = not inside
            j = i
        if inside:
            return True, zone["name"]
    return False, None

def is_arrival_flight(flight):
    """
    Simple check if a flight is arriving to BKK:
    - Below 10,000 feet (3048 meters)
    - Descending (negative vertical rate)
    - Within 80km of airport
    """
    lat = flight[6]
    lon = flight[5]
    altitude = flight[7]  # barometric altitude in meters
    vertical_rate = flight[11]
    
    if lat is None or lon is None or altitude is None:
        return False
    
    # Calculate distance to airport
    distance = calculate_distance(lat, lon, BKK_LAT, BKK_LON)
    
    # Consider as arrival if:
    # 1. Below 10,000 feet / 3048 meters
    # 2. Within 80km of airport
    # 3. Descending OR level flight below 5,000 feet
    is_below_arrival_alt = altitude < 3048  # Below 10,000 feet
    is_close_to_airport = distance < 80     # Within 80km
    is_descending = vertical_rate is not None and vertical_rate < -1.0
    is_final_approach = altitude < 1524 and distance < 30  # Below 5,000 feet and within 30km
    
    return is_below_arrival_alt and is_close_to_airport and (is_descending or is_final_approach)

def estimate_arrival_time(flight):
    """Estimate arrival time based on distance and speed"""
    lat = flight[6]
    lon = flight[5]
    velocity = flight[9]  # m/s
    
    if lat is None or lon is None or velocity is None or velocity < 10:
        return None
    
    # Calculate distance to airport in km
    distance = calculate_distance(lat, lon, BKK_LAT, BKK_LON)
    
    # Convert velocity from m/s to km/h
    velocity_kmh = velocity * 3.6
    
    # Estimate time in hours
    time_hours = distance / velocity_kmh
    
    # Convert to minutes
    time_minutes = time_hours * 60
    
    # Get current time
    now = datetime.datetime.now()
    
    # Add estimated time to current time
    eta = now + datetime.timedelta(minutes=time_minutes)
    
    return {
        "distance_km": distance,
        "eta": eta,
        "minutes_to_arrival": time_minutes
    }

def process_arrivals(flights):
    """Process and sort arrival flights"""
    arrivals = []
    
    for flight in flights:
        if not flight or len(flight) < 12:
            continue
            
        if not all([flight[5], flight[6], flight[7]]):  # Skip if missing position/altitude
            continue
            
        if is_arrival_flight(flight):
            # Get callsign and clean it
            callsign = flight[1].strip() if flight[1] else "Unknown"
            
            # Get estimated arrival time
            eta_data = estimate_arrival_time(flight)
            if not eta_data:
                continue
                
            # Check if in echo zone
            in_echo, echo_name = is_in_echo_zone(flight[6], flight[5])
            
            # Parse airline code and flight number
            airline_code = ""
            flight_number = ""
            
            if callsign:
                # Most airline callsigns follow a pattern of 3 letters followed by numbers
                digits_start = 0
                for i, char in enumerate(callsign):
                    if char.isdigit():
                        digits_start = i
                        break
                
                if digits_start > 0:
                    airline_code = callsign[:digits_start]
                    flight_number = callsign[digits_start:]
            
            # Get heading/direction
            heading = flight[10]  # True track in decimal degrees
            direction = "Unknown"
            if heading is not None:
                # Convert numeric heading to cardinal direction
                directions = ["N", "NE", "E", "SE", "S", "SW", "W", "NW", "N"]
                index = round(heading / 45) % 8
                direction = directions[index]
            
            # Add to arrivals list
            arrivals.append({
                "flight": flight,
                "callsign": callsign,
                "eta_data": eta_data,
                "in_echo": in_echo,
                "echo_name": echo_name,
                "direction": direction,
                "heading": heading,
                "airline_code": airline_code,
                "flight_number": flight_number
            })
    
    # Sort by estimated arrival time
    arrivals.sort(key=lambda x: x["eta_data"]["minutes_to_arrival"])
    
    return arrivals

def display_arrival_info(arrival_data):
    """Format arrival information for display"""
    flight = arrival_data["flight"]
    callsign = arrival_data["callsign"]
    eta_data = arrival_data["eta_data"]
    in_echo = arrival_data["in_echo"]
    echo_name = arrival_data["echo_name"]
    direction = arrival_data["direction"]
    
    # Extract flight data
    icao24 = flight[0]
    alt_m = flight[7]
    alt_ft = int(alt_m * 3.28084) if alt_m is not None else None
    velocity_ms = flight[9]
    velocity_kts = int(velocity_ms * 1.94384) if velocity_ms is not None else None
    vertical_rate = flight[11]
    vertical_fpm = int(vertical_rate * 196.85) if vertical_rate is not None else None
    squawk = flight[14] if len(flight) > 14 and flight[14] else "----"
    
    # Format arrival time
    eta_time = eta_data["eta"].strftime("%H:%M:%S")
    minutes_to_arrival = int(eta_data["minutes_to_arrival"])
    
    # Weather status indicator
    weather_status = f"⚠️ {echo_name}" if in_echo else "✅ Clear"
    
    # Build compact output string
    info = f"🛬 {callsign} | DIR: {direction} | ETA: {eta_time} ({minutes_to_arrival} min) | {weather_status}"
    info += f"\n  ALT: {alt_ft} ft | SPD: {velocity_kts} kts | DIST: {eta_data['distance_km']:.1f} km"
    info += f"\n  SQUAWK: {squawk} | ICAO: {icao24}"
    
    return info

def main():
    print("BKK/VTBS Flight Monitoring - Simplified")
    print("======================================")
    print(f"Time: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Get flights
    flights = get_flights_near_bkk()
    
    if not flights:
        print("No flights found or error fetching data.")
        return
    
    # Process arrivals
    arrivals = process_arrivals(flights)
    
    # Display arrivals in order of ETA
    print(f"Found {len(arrivals)} arriving flights to BKK/VTBS:\n")
    
    if not arrivals:
        print("No arrival flights detected.")
        return
    
    print("ARRIVING FLIGHTS (sorted by ETA):")
    print("--------------------------------")
    
    for i, arrival in enumerate(arrivals, 1):
        print(f"#{i}: {display_arrival_info(arrival)}")
        print()
    
    # Display summary
    weather_affected = sum(1 for a in arrivals if a["in_echo"])
    print("\nSUMMARY:")
    print(f"Total arrivals: {len(arrivals)}")
    print(f"Weather affected: {weather_affected} ({weather_affected/len(arrivals)*100:.1f}%)" if arrivals else "Weather affected: 0 (0%)")
    print(f"Arrival window: {arrivals[0]['eta_data']['eta'].strftime('%H:%M')} to {arrivals[-1]['eta_data']['eta'].strftime('%H:%M')}" if arrivals else "No arrivals")

if __name__ == "__main__":
    main()