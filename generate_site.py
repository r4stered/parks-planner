"""
Generate a deployable static site with park data embedded.
This creates an index.html file ready to host on your personal site.
"""

import json
import os
import re
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent
PARKS_FILE = BASE_DIR / "res" / "parks.json"
DRIVE_TIMES_FILE = BASE_DIR / "res" / "drive_times.json"
TEMPLATE_FILE = BASE_DIR / "output" / "index.html"
OUTPUT_FILE = BASE_DIR / "output" / "parks_site.html"

# Configuration - Update these with your actual values
FIREBASE_CONFIG = {
    "apiKey": os.getenv("FIREBASE_API_KEY", "YOUR_FIREBASE_API_KEY"),
    "authDomain": os.getenv("FIREBASE_AUTH_DOMAIN", "YOUR_PROJECT.firebaseapp.com"),
    "databaseURL": os.getenv("FIREBASE_DATABASE_URL", "https://YOUR_PROJECT-default-rtdb.firebaseio.com"),
    "projectId": os.getenv("FIREBASE_PROJECT_ID", "YOUR_PROJECT"),
    "storageBucket": os.getenv("FIREBASE_STORAGE_BUCKET", "YOUR_PROJECT.appspot.com"),
    "messagingSenderId": os.getenv("FIREBASE_MESSAGING_SENDER_ID", "YOUR_SENDER_ID"),
    "appId": os.getenv("FIREBASE_APP_ID", "YOUR_APP_ID"),
}

# Home location - using general Santa Cruz area for privacy
HOME_LAT = 36.9741  # Santa Cruz downtown area (general location)
HOME_LNG = -122.0308  # Santa Cruz downtown area (general location) 
HOME_ADDRESS = "Santa Cruz, CA"  # General area only


def load_json(file_path: Path) -> dict:
    """Load JSON file."""
    if file_path.exists():
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def generate_site():
    """Generate the deployable HTML file."""
    print("Loading park data...")
    parks = load_json(PARKS_FILE)
    drive_times = load_json(DRIVE_TIMES_FILE)

    print(f"  Loaded {len(parks)} parks")
    print(f"  Loaded {len(drive_times)} drive times")

    print("Reading template...")
    with open(TEMPLATE_FILE, "r", encoding="utf-8") as f:
        template = f.read()

    print("Embedding data...")

    # Replace placeholders with actual data
    parks_json = json.dumps(parks, indent=2)
    drive_times_json = json.dumps(drive_times, indent=2)

    template = template.replace("PARKS_PLACEHOLDER", parks_json)
    template = template.replace("DRIVE_TIMES_PLACEHOLDER", drive_times_json)

    # Update Firebase config
    firebase_config_str = f"""{{
                apiKey: "{FIREBASE_CONFIG['apiKey']}",
                authDomain: "{FIREBASE_CONFIG['authDomain']}",
                databaseURL: "{FIREBASE_CONFIG['databaseURL']}",
                projectId: "{FIREBASE_CONFIG['projectId']}",
                storageBucket: "{FIREBASE_CONFIG['storageBucket']}",
                messagingSenderId: "{FIREBASE_CONFIG['messagingSenderId']}",
                appId: "{FIREBASE_CONFIG['appId']}"
            }}"""

    template = re.sub(
        r'firebase: \{[^}]+\}',
        f'firebase: {firebase_config_str}',
        template
    )

    # Update home location with general coordinates
    home_config_str = f"""{{
                lat: {HOME_LAT},
                lng: {HOME_LNG},
                address: "{HOME_ADDRESS}"
            }}"""

    template = re.sub(
        r'home: \{[^}]+\}',
        f'home: {home_config_str}',
        template
    )

    print("Writing output file...")
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(template)

    print(f"\nGenerated: {OUTPUT_FILE}")

if __name__ == "__main__":
    generate_site()
