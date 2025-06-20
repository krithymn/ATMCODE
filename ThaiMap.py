#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon May 19 11:32:25 2025
@author: shiba
"""
import matplotlib.pyplot as plt
import numpy as np

path_source = "C:/Users/krith/Desktop/ATMCODE/Map"
path_map = path_source + "/VTBS・BKK/thailand_outline.csv"

# Read all coordinate data
all_lon = []
all_lat = []

with open(path_map, "r", encoding="utf-8_sig") as frMAP:
    for i in range(0, 13538):
        readcell = frMAP.readline()
        try:
            lonlat = readcell.split(",")
            if len(lonlat) >= 2:
                lon_tmp = float(lonlat[0])
                lat_tmp = float(lonlat[1])
                # Filter out coordinates that are clearly outside Thailand
                if 95 <= lon_tmp <= 110 and 5 <= lat_tmp <= 25:
                    all_lon.append(lon_tmp)
                    all_lat.append(lat_tmp)
        except ValueError:
            continue

print(f"Total valid coordinates: {len(all_lon)}")

# Now automatically detect jumps and split into segments
segments = []  # Will store (lon_list, lat_list) tuples
current_lon = [all_lon[0]]
current_lat = [all_lat[0]]

# Define what constitutes a "jump" (distance threshold)
jump_threshold = 0.5  # degrees

for i in range(1, len(all_lon)):
    # Calculate distance from previous point
    lon_diff = abs(all_lon[i] - all_lon[i-1])
    lat_diff = abs(all_lat[i] - all_lat[i-1])
    
    # If the jump is too large, start a new segment
    if lon_diff > jump_threshold or lat_diff > jump_threshold:
        # Save current segment if it has enough points
        if len(current_lon) > 10:
            segments.append((current_lon, current_lat))
        
        # Start new segment
        current_lon = [all_lon[i]]
        current_lat = [all_lat[i]]
    else:
        # Continue current segment
        current_lon.append(all_lon[i])
        current_lat.append(all_lat[i])

# Don't forget the last segment
if len(current_lon) > 10:
    segments.append((current_lon, current_lat))

print(f"Total segments after jump detection: {len(segments)}")

# Create the plot
plt.figure(figsize=(10, 10))
plt.gca().set_aspect('equal')
output_title = "Thai border"
plt.title(output_title, fontsize=12)
plt.xlim(95, 110)
plt.ylim(5, 25)
plt.tick_params(labelsize=10)
plt.grid(True)
plt.xlabel('Longitude', fontsize=12)
plt.ylabel('Latitude', fontsize=12)

# Plot each segment in black
for i, (lon_seg, lat_seg) in enumerate(segments):
    plt.plot(lon_seg, lat_seg, color='black', linewidth=1.0)

plt.show()

# Print segment info for reference
print(f"Map plotted with {len(segments)} segments in black")