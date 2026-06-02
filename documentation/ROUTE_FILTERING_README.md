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

## 4. How UTM Works: The Transverse Cylinder
Imagine wrapping a piece of paper in the shape of a cylinder around the Earth (like an orange). 
Instead of wrapping it horizontally along the Equator (a classic projection), UTM wraps it **vertically**, passing through both poles. This is called a "Transverse" projection.

The paper touches the Earth perfectly along a single vertical line, called the *Central Meridian*. On this contact line, the projection is perfect: there is absolutely zero distortion.

### 4.1. The 60 Vertical "Slices" (UTM Zones)
If we were to project the entire world onto this single cylinder, countries far away from the contact line would appear stretched and distorted (a country on the edge would look gigantic).
To maintain extreme precision, UTM "cheats": it slices the Earth into **60 vertical zones**, like segments of an orange, each being 6 degrees wide.

For each zone, we rotate the cylinder so that it touches exactly the center of that specific 6-degree slice.
Within this narrow band, the distortion is almost non-existent (about 1 meter of error for every 2,500 meters).

### 4.2. Mathematical Transformation (Degrees to Meters)
Once we isolate our small 6-degree corridor and project our map onto the cylinder, we unroll the paper flat. We then draw a standard X and Y grid:

* **The Y-axis (Northing):** This is simply the distance in meters from the Equator. If you are 3,500,000 meters north of the equator, your Y = 3,500,000. *(For the southern hemisphere, to avoid negative numbers, the South Pole is treated as point 0, putting the Equator at 10,000,000 meters).*
* **The X-axis (Easting):** The center of your vertical slice (the Central Meridian) acts as the vertical axis. To ensure we never deal with negative numbers when moving west, UTM arbitrarily assigns the value X = 500,000 meters to this central meridian. If you are 50 km west of the center, your X is 450,000. If you are 50 km east, your X is 550,000.

---

## 5. The Polar Problem and the UPS Solution
There is a fundamental geometric flaw with this vertical cylinder approach: as you get closer to the poles, the vertical meridian lines converge and the 6-degree bands become tiny and unusable. 

Here is how reality handles this glitch:

1. **UTM stops before the poles:** Because the system turns chaotic at the extremes, cartographers made a strict rule: UTM is officially cut off at the poles. The UTM grid only covers the Earth between 80° South and 84° North latitude. (They pushed it to 84° North just to fit all of Greenland and Northern Canada). If your algorithm tries to calculate UTM coordinates beyond these limits, it will crash or return absurd numbers.
2. **The Backup System: UPS (Universal Polar Stereographic):** For polar zones (Antarctica in the south, and the Arctic Ocean in the north), the UTM cylinder is abandoned in favor of its sibling system, the UPS.
   * **The flat sheet:** Instead of wrapping a cylinder around the Earth, imagine placing a completely flat sheet of paper balancing directly on top of the North Pole (like a flat hat).
   * **The projection:** The "light source" is placed at the opposite pole, projecting the shadows of the continents straight up onto this flat sheet.
   * **The result:** This creates a perfect circular map, ideal for mapping the poles without crushing them.

*In summary for your code: Currently, the application maps local roads far from the poles, making UTM flawless and extremely accurate. However, if the organization someday decides to scan trail signs on snowmobile paths at the North Pole, the spatial filtering code will throw an error and will need to implement a switch to a polar projection (UPS).*

---

## 6. The Overall Process (Step by Step)

Here is how the magic happens invisibly after the machine learning pipeline:

1. **Initial Extraction (In Degrees):**
   The system detected 100 signs, each with its GPS coordinates (Lat/Lon in WGS84 degrees).
   The organization provided its road network in GeoJSON (also in Lat/Lon).

2. **Magic Reprojection (2D Plane Generation):**
   Our system automatically determines the ideal UTM zone for the analyzed region. 
   It then re-projects all the roads and detected signs onto this 2D grid where "1 mathematical unit = 1 physical meter".

3. **Buffer Creation:**
   Now that it represents a grid in meters, the algorithm digitally "draws" a precise 50-meter corridor on each side of the road network.

### Important Geometry Detail: Why the 50 m corridor is perpendicular to the route

This perpendicular behavior is automatic once geometries are projected in UTM (meters).

In code, the route filtering service applies a geometric buffer operation on each route LineString (equivalent to `line.buffer(50)`).
Mathematically, a line buffer is the set of all points located at a distance of at most 50 meters from the line center.

That means the corridor is built using the **local normal direction** of the line at every point (i.e. locally perpendicular to the route direction):
- on straight segments, it is exactly perpendicular to the segment;
- on curves, the normal rotates continuously, so the corridor follows the curve smoothly;
- no fixed global X/Y offset is used.

So we do **not** manually compute route angles or perpendicular vectors in application code. The geometry engine computes this correctly from the route shape, as long as the operation is done in a metric CRS (UTM), not directly in WGS84 degrees.

4. **Spatial Sorting (Intersection):**
   The system overlaps the position of the points (the detected signs) with the surface of this corridor. 
   * If the sign falls inside the corridor ➔ **It is kept**.
   * If the sign falls outside ➔ **It is excluded** (it is considered to be on another road).

5. **Back to Reality (De-projection):**
   The points that survived the sorting are saved in the `signs_merged_filtered.csv` file. Their original coordinates in WGS84 Degrees are obviously preserved so they can be displayed correctly on an interactive web map!

---

*In summary: we transform the round earth into a sheet of grid paper in meters (UTM Reprojection), we draw the boundaries with a marker (50m Buffer), we erase anything outside the lines, and then we put the remaining signs back on the spherical earth.*