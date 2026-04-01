# Explanation of the Route Filtering System

This document explains the overall functionality of the traffic sign filtering system based on an organization's road network. It specifically describes why and how "spatial reprojection" is used to guarantee filtering accuracy.

---

## 1. The Goal of Filtering

When a vehicle records a video, the camera detects all signs present in its field of view. This includes signs on the main road, but also those on perpendicular streets, private roads, or adjacent parking lots.

The goal of the Organization is often to **keep only the signs that strictly belong to its official road network** (its "Routes").

To do this, we upload a file containing the GPS paths of the organization's roads (a GeoJSON file), and we compare the coordinates of each detected sign against this road network.

---

## 2. The Problem: "Meters" vs "Degrees"

One might think it's enough to simply check the distance between the sign and the road. To do this, we want to create a "corridor" (a **Buffer** in cartography) that is 50 meters wide around the road paths, to account for the roadside and GPS inaccuracy.

**The fundamental problem with GPS (WGS84):**
GPS coordinates (Longitude / Latitude) are expressed in **degrees** measured on a sphere (the Earth). However, a "degree" does not always represent the same distance depending on where you are:
* 1 degree of Latitude is roughly 111 km everywhere.
* But 1 degree of Longitude varies wildly: it is ~111 km at the Equator, but drops to 0 km at the poles.

If we tried to ask the system to "create a 50-meter corridor" working directly with classic GPS coordinates, the system wouldn't understand because its base unit is the *angular degree*, not the *absolute meter*. The results would be completely distorted (an elongated oval-shaped corridor).

---

## 3. The Solution: Spatial Reprojection (UTM System)

To be able to make reliable distance calculations in meters, and not in degrees, we must "flatten" the relevant earthly area onto a 2D grid in meters. This is called **Reprojection**.

We use the **UTM (Universal Transverse Mercator)** geographic system. 
UTM cuts the Earth into 60 small vertical zones. Once we determine which specific UTM zone the road is in (for example, the local zone around Atlanta or Paris), we can mathematically transform our degrees (Latitude/Longitude) into X/Y coordinates (in meters) on a flat map.

### Why is this crucial?
By projecting our data into UTM:
1. **The unit of measurement becomes the meter** equally in all directions (X and Y).
2. We can then draw a perfect circle (or a perfect corridor) with a **50-meter radius** around the road completely mathematically, without any geographic distortion.

---

## 4. The Overall Process (Step by Step)

Here is how the magic happens invisibly after the machine learning pipeline:

1. **Initial Extraction (In Degrees):**
   The system detected 100 signs, each with its GPS coordinates (Lat/Lon in WGS84 degrees).
   The organization provided its road network in GeoJSON (also in Lat/Lon).

2. **Magic Reprojection (2D Plane Generation):**
   Our system automatically determines the ideal UTM zone for the analyzed region. 
   It then re-projects all the roads and detected signs onto this 2D grid where "1 mathematical unit = 1 physical meter".

3. **Buffer Creation:**
   Now that it represents a grid in meters, the algorithm digitally "draws" a precise 50-meter corridor on each side of the road network.

4. **Spatial Sorting (Intersection):**
   The system overlaps the position of the points (the detected signs) with the surface of this corridor. 
   * If the sign falls inside the corridor ➔ **It is kept**.
   * If the sign falls outside ➔ **It is excluded** (it is considered to be on another road).

5. **Back to Reality (De-projection):**
   The points that survived the sorting are saved in the `signs_merged_filtered.csv` file. Their original coordinates in WGS84 Degrees are obviously preserved so they can be displayed correctly on an interactive web map!

---

*In summary: we transform the round earth into a sheet of grid paper in meters (UTM Reprojection), we draw the boundaries with a marker (50m Buffer), we erase anything outside the lines, and then we put the remaining signs back on the spherical earth.*