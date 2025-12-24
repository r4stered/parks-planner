"""Generate the site and serve it locally."""

import http.server
import os
import socketserver
import subprocess
import sys
import webbrowser
from pathlib import Path


def main():
    """Generate site and start local server."""
    base_dir = Path(__file__).parent

    # Generate the site first
    print("Generating site...")
    result = subprocess.run(
        [sys.executable, str(base_dir / "generate_site.py")],
        cwd=base_dir,
    )

    if result.returncode != 0:
        print("Failed to generate site")
        return

    # Change to output directory
    output_dir = base_dir / "output"
    os.chdir(output_dir)

    # Start server
    port = 8000
    handler = http.server.SimpleHTTPRequestHandler

    with socketserver.TCPServer(("", port), handler) as httpd:
        url = f"http://localhost:{port}/parks_site.html"
        print(f"\nServing at {url}")
        print("Press Ctrl+C to stop\n")

        # Open browser
        webbrowser.open(url)

        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nServer stopped")


if __name__ == "__main__":
    main()
