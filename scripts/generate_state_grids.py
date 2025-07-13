#!/usr/bin/env python3
"""Generate grid points for all US states from GeoJSON files."""

import json
from pathlib import Path

from app.models.geographic import BoundingBox
from app.scraper.utils import ScraperUtils

# Set up paths
STATES_DIR = Path("docs/GeoJson/States")
OUTPUT_DIR = Path("outputs/state_grids")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def main() -> None:
    """Generate grid points for each state."""
    # Get all state GeoJSON files
    state_files = sorted(STATES_DIR.glob("*_zip_codes_geo.min.json"))

    # Process each state
    total_points = 0
    for state_file in state_files:
        # Extract state code from filename (e.g., "ca" from "ca_california_zip_codes_geo.min.json")
        state_code = state_file.name.split("_")[0]

        print(f"\nProcessing {state_code.upper()}...")

        try:
            # Generate grid points
            points = ScraperUtils.get_grid_points_from_geojson(state_file)
            total_points += len(points)

            # Save points to JSON
            output_file = OUTPUT_DIR / f"{state_code}_grid.json"
            with open(output_file, "w") as f:
                json.dump(
                    [
                        {
                            "latitude": p.latitude,
                            "longitude": p.longitude,
                            "name": p.name,
                        }
                        for p in points
                    ],
                    f,
                    indent=2,
                )

            print(f"  Generated {len(points)} points")
            print(f"  Saved to {output_file}")

            # Get bounding box for verification
            bounds = BoundingBox.from_geojson(state_file)
            print(f"  Bounds: {bounds.name}")

        except Exception as e:
            print(f"  Error processing {state_code}: {e}")

    print(f"\nComplete! Generated {total_points} total points across all states")


if __name__ == "__main__":
    main()
