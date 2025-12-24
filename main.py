import json
import os
import time
from pathlib import Path
from math import radians, sin, cos, sqrt, atan2

import folium  # type: ignore
import googlemaps  # type: ignore
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")
# Use general area instead of specific address for privacy
MY_ADDRESS = "Santa Cruz, CA"

# Paths
BASE_DIR = Path(__file__).parent
PARKS_FILE = BASE_DIR / "res" / "parks.json"
DRIVE_TIMES_FILE = BASE_DIR / "res" / "drive_times.json"
OUTPUT_DIR = BASE_DIR / "output"
MAP_FILE = OUTPUT_DIR / "parks_map.html"
REPORT_FILE = OUTPUT_DIR / "trip_report.txt"

# Clustering threshold in miles
CLUSTER_THRESHOLD_MILES = 30


def load_parks() -> dict:
    """Load parks from JSON file."""
    with open(PARKS_FILE, "r") as f:
        return json.load(f)


def save_parks(parks: dict) -> None:
    """Save parks to JSON file."""
    with open(PARKS_FILE, "w") as f:
        json.dump(parks, f, indent=4)


def load_drive_times() -> dict:
    """Load cached drive times if available."""
    if DRIVE_TIMES_FILE.exists():
        with open(DRIVE_TIMES_FILE, "r") as f:
            return json.load(f)
    return {}


def save_drive_times(drive_times: dict) -> None:
    """Save drive times to cache file."""
    DRIVE_TIMES_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(DRIVE_TIMES_FILE, "w") as f:
        json.dump(drive_times, f, indent=4)


def geocode_parks(gmaps: googlemaps.Client, parks: dict) -> dict:
    """Geocode parks that don't have coordinates yet."""
    updated = False
    for park_name, value in parks.items():
        if value == "Y":
            # Need to geocode this park
            search_query = f"{park_name}, California"
            print(f"Geocoding: {park_name}...")
            try:
                result = gmaps.geocode(search_query)
                if result:
                    location = result[0]["geometry"]["location"]
                    parks[park_name] = {"lat": location["lat"], "lng": location["lng"]}
                    updated = True
                    print(f"  Found: {location['lat']}, {location['lng']}")
                else:
                    print(f"  WARNING: Could not geocode {park_name}")
                    parks[park_name] = {"lat": None, "lng": None, "error": "Not found"}
                    updated = True
                # Rate limit to avoid API throttling
                time.sleep(0.1)
            except Exception as e:
                print(f"  ERROR geocoding {park_name}: {e}")
                parks[park_name] = {"lat": None, "lng": None, "error": str(e)}
                updated = True

    if updated:
        save_parks(parks)
        print("Parks file updated with coordinates.")

    return parks


def geocode_home(gmaps: googlemaps.Client) -> tuple[float, float]:
    """Geocode the home address."""
    print(f"Geocoding home address: {MY_ADDRESS}...")
    result = gmaps.geocode(MY_ADDRESS)
    if result:
        location = result[0]["geometry"]["location"]
        print(f"  Found: {location['lat']}, {location['lng']}")
        return location["lat"], location["lng"]
    raise ValueError(f"Could not geocode home address: {MY_ADDRESS}")


def get_drive_times(
    gmaps: googlemaps.Client, home_coords: tuple[float, float], parks: dict
) -> dict:
    """Get drive times from home to each park using Distance Matrix API."""
    drive_times = load_drive_times()
    updated = False

    for park_name, coords in parks.items():
        if park_name in drive_times:
            continue  # Already cached

        if not isinstance(coords, dict) or coords.get("lat") is None:
            continue  # Skip parks without valid coordinates

        print(f"Getting drive time to: {park_name}...")
        try:
            result = gmaps.distance_matrix(
                origins=[f"{home_coords[0]},{home_coords[1]}"],
                destinations=[f"{coords['lat']},{coords['lng']}"],
                mode="driving",
            )

            if result["rows"][0]["elements"][0]["status"] == "OK":
                element = result["rows"][0]["elements"][0]
                drive_times[park_name] = {
                    "duration_seconds": element["duration"]["value"],
                    "duration_text": element["duration"]["text"],
                    "distance_meters": element["distance"]["value"],
                    "distance_text": element["distance"]["text"],
                }
                print(
                    f"  {element['duration']['text']} ({element['distance']['text']})"
                )
            else:
                drive_times[park_name] = {"error": "Route not found"}
                print(f"  WARNING: Could not find route")

            updated = True
            # Rate limit
            time.sleep(0.1)

        except Exception as e:
            print(f"  ERROR: {e}")
            drive_times[park_name] = {"error": str(e)}
            updated = True

    if updated:
        save_drive_times(drive_times)
        print("Drive times cache updated.")

    return drive_times


def haversine_distance(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Calculate distance between two points in miles using Haversine formula."""
    R = 3959  # Earth's radius in miles

    lat1, lng1, lat2, lng2 = map(radians, [lat1, lng1, lat2, lng2])
    dlat = lat2 - lat1
    dlng = lng2 - lng1

    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlng / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))

    return R * c


def cluster_parks(parks: dict, threshold_miles: float = CLUSTER_THRESHOLD_MILES) -> list[list[str]]:
    """Group parks within threshold distance of each other."""
    valid_parks = [
        (name, coords)
        for name, coords in parks.items()
        if isinstance(coords, dict) and coords.get("lat") is not None
    ]

    clusters = []
    assigned = set()

    for name, coords in valid_parks:
        if name in assigned:
            continue

        # Start a new cluster with this park
        cluster = [name]
        assigned.add(name)

        # Find all parks within threshold
        for other_name, other_coords in valid_parks:
            if other_name in assigned:
                continue

            distance = haversine_distance(
                coords["lat"], coords["lng"], other_coords["lat"], other_coords["lng"]
            )

            if distance <= threshold_miles:
                cluster.append(other_name)
                assigned.add(other_name)

        clusters.append(cluster)

    return clusters


def get_park_type(park_name: str) -> str:
    """Determine park type from name suffix."""
    if "SHP" in park_name:
        return "historical"
    elif "SB" in park_name:
        return "beach"
    elif "SRA" in park_name:
        return "recreation"
    elif "SNR" in park_name:
        return "reserve"
    else:
        return "park"


def get_marker_color(duration_seconds: int | None) -> str:
    """Get marker color based on drive time."""
    if duration_seconds is None:
        return "gray"
    hours = duration_seconds / 3600
    if hours < 2:
        return "green"
    elif hours < 4:
        return "orange"
    else:
        return "red"


def get_marker_icon(park_type: str) -> str:
    """Get icon name based on park type."""
    icons = {
        "beach": "umbrella-beach",
        "historical": "landmark",
        "recreation": "campground",
        "reserve": "leaf",
        "park": "tree",
    }
    return icons.get(park_type, "tree")


def generate_map(
    home_coords: tuple[float, float], parks: dict, drive_times: dict
) -> None:
    """Generate interactive Folium map."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Center map on California
    m = folium.Map(location=[37.5, -119.5], zoom_start=6)

    # Add home marker
    folium.Marker(
        location=home_coords,
        popup=f"<b>Home</b><br>{MY_ADDRESS}",
        icon=folium.Icon(color="blue", icon="home", prefix="fa"),
    ).add_to(m)

    # Add park markers
    for park_name, coords in parks.items():
        if not isinstance(coords, dict) or coords.get("lat") is None:
            continue

        park_type = get_park_type(park_name)
        drive_info = drive_times.get(park_name, {})
        duration_seconds = drive_info.get("duration_seconds")
        color = get_marker_color(duration_seconds)

        # Build popup content
        popup_html = f"<b>{park_name}</b><br>"
        if "duration_text" in drive_info:
            popup_html += f"Drive: {drive_info['duration_text']}<br>"
            popup_html += f"Distance: {drive_info['distance_text']}"
        elif "error" in drive_info:
            popup_html += f"<i>Route unavailable</i>"

        folium.Marker(
            location=[coords["lat"], coords["lng"]],
            popup=folium.Popup(popup_html, max_width=300),
            icon=folium.Icon(color=color, icon=get_marker_icon(park_type), prefix="fa"),
        ).add_to(m)

    m.save(str(MAP_FILE))
    print(f"Map saved to: {MAP_FILE}")


def categorize_trip(duration_seconds: int | None) -> str:
    """Categorize trip based on drive time."""
    if duration_seconds is None:
        return "Unknown"
    hours = duration_seconds / 3600
    if hours < 3:
        return "Day Trip"
    elif hours < 5:
        return "Weekend Trip"
    else:
        return "Multi-day Trip"


def generate_report(parks: dict, drive_times: dict, clusters: list[list[str]]) -> None:
    """Generate trip planning report."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Sort parks by drive time
    sorted_parks = []
    for park_name in parks.keys():
        info = drive_times.get(park_name, {})
        duration = info.get("duration_seconds", float("inf"))
        sorted_parks.append((park_name, duration, info))

    sorted_parks.sort(key=lambda x: x[1])

    # Group by category
    categories = {"Day Trip": [], "Weekend Trip": [], "Multi-day Trip": [], "Unknown": []}

    for park_name, duration, info in sorted_parks:
        category = categorize_trip(info.get("duration_seconds"))
        categories[category].append((park_name, info))

    # Build report
    lines = []
    lines.append("=" * 60)
    lines.append("CALIFORNIA STATE PARKS TRIP PLANNER")
    lines.append("=" * 60)
    lines.append(f"\nStarting from: {MY_ADDRESS}")
    lines.append(f"Total parks: {len(parks)}")
    lines.append("")

    # Summary
    lines.append("-" * 60)
    lines.append("SUMMARY BY TRIP TYPE")
    lines.append("-" * 60)
    for category in ["Day Trip", "Weekend Trip", "Multi-day Trip", "Unknown"]:
        count = len(categories[category])
        if count > 0:
            lines.append(f"  {category}: {count} parks")
    lines.append("")

    # Detailed listings
    for category in ["Day Trip", "Weekend Trip", "Multi-day Trip"]:
        if not categories[category]:
            continue

        lines.append("-" * 60)
        lines.append(f"{category.upper()}S (sorted by drive time)")
        lines.append("-" * 60)

        for park_name, info in categories[category]:
            duration = info.get("duration_text", "N/A")
            distance = info.get("distance_text", "N/A")
            lines.append(f"  {park_name}")
            lines.append(f"    Drive: {duration} | Distance: {distance}")
        lines.append("")

    # Multi-day trip clusters
    multi_day_clusters = [
        c for c in clusters if len(c) > 1 and any(
            categorize_trip(drive_times.get(p, {}).get("duration_seconds")) == "Multi-day Trip"
            for p in c
        )
    ]

    if multi_day_clusters:
        lines.append("-" * 60)
        lines.append("SUGGESTED MULTI-DAY TRIP CLUSTERS")
        lines.append("(Parks within 30 miles of each other)")
        lines.append("-" * 60)

        for i, cluster in enumerate(multi_day_clusters, 1):
            lines.append(f"\n  Cluster {i}: ({len(cluster)} parks)")
            for park_name in cluster:
                info = drive_times.get(park_name, {})
                duration = info.get("duration_text", "N/A")
                lines.append(f"    - {park_name} ({duration})")

    lines.append("")
    lines.append("=" * 60)
    lines.append("Map available at: output/parks_map.html")
    lines.append("=" * 60)

    report_text = "\n".join(lines)

    # Print to console
    print("\n" + report_text)

    # Save to file
    with open(REPORT_FILE, "w") as f:
        f.write(report_text)
    print(f"\nReport saved to: {REPORT_FILE}")


def main():
    """Main entry point."""
    if not GOOGLE_MAPS_API_KEY:
        print("ERROR: GOOGLE_MAPS_API_KEY not set in .env file")
        print("Please copy .env.example to .env and add your API key")
        return

    if not MY_ADDRESS:
        print("ERROR: MY_ADDRESS not set in .env file")
        print("Please copy .env.example to .env and add your address")
        return

    print("California State Parks Trip Planner")
    print("=" * 40)

    # Initialize Google Maps client
    gmaps = googlemaps.Client(key=GOOGLE_MAPS_API_KEY)

    # Load and geocode parks
    print("\n[1/5] Loading and geocoding parks...")
    parks = load_parks()
    parks = geocode_parks(gmaps, parks)

    # Geocode home address
    print("\n[2/5] Geocoding home address...")
    home_coords = geocode_home(gmaps)

    # Get drive times
    print("\n[3/5] Calculating drive times...")
    drive_times = get_drive_times(gmaps, home_coords, parks)

    # Cluster parks
    print("\n[4/5] Clustering parks for multi-day trips...")
    clusters = cluster_parks(parks)
    print(f"  Found {len(clusters)} clusters")

    # Generate outputs
    print("\n[5/5] Generating map and report...")
    generate_map(home_coords, parks, drive_times)
    generate_report(parks, drive_times, clusters)

    print("\nDone! Open output/parks_map.html in your browser to view the map.")


if __name__ == "__main__":
    main()
