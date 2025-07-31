#!/bin/bash
# Mock docker compose for testing bouy functionality
# This script simulates docker compose behavior for testing

# Helper function to output JSON
output_json() {
    echo "$1"
}

# Parse the command arguments
case "$*" in
    # Service status checks
    *"ps --format json"*)
        if [[ "$*" == *"app"* ]]; then
            output_json '[{"Name": "app", "State": "running", "Status": "Up 2 hours", "Health": "healthy"}]'
        elif [[ "$*" == *"db"* ]]; then
            output_json '[{"Name": "db", "State": "running", "Status": "Up 2 hours"}]'
        elif [[ "$*" == *"cache"* ]]; then
            output_json '[{"Name": "cache", "State": "running", "Status": "Up 2 hours"}]'
        elif [[ "$*" == *"worker"* ]]; then
            output_json '[{"Name": "worker", "State": "running", "Status": "Up 1 hour"}]'
        elif [[ "$*" == *"scraper"* ]]; then
            output_json '[{"Name": "scraper", "State": "running", "Status": "Up 30 minutes"}]'
        elif [[ "$*" == *"reconciler"* ]]; then
            output_json '[{"Name": "reconciler", "State": "running", "Status": "Up 15 minutes"}]'
        elif [[ "$*" == *"recorder"* ]]; then
            output_json '[{"Name": "recorder", "State": "running", "Status": "Up 10 minutes"}]'
        elif [[ "$*" == *"haarrrvest-publisher"* ]]; then
            output_json '[{"Name": "haarrrvest-publisher", "State": "running", "Status": "Up 5 minutes"}]'
        else
            # Return all services
            output_json '[
                {"Name": "app", "State": "running", "Status": "Up 2 hours", "Health": "healthy"},
                {"Name": "db", "State": "running", "Status": "Up 2 hours"},
                {"Name": "cache", "State": "running", "Status": "Up 2 hours"},
                {"Name": "worker", "State": "running", "Status": "Up 1 hour"}
            ]'
        fi
        exit 0
        ;;

    # Text format ps
    *"ps"*)
        echo "NAME                      STATUS    PORTS"
        echo "pantry-pirate-radio-app-1     Up        0.0.0.0:8000->8000/tcp"
        echo "pantry-pirate-radio-db-1      Up        5432/tcp"
        echo "pantry-pirate-radio-cache-1   Up        6379/tcp"
        echo "pantry-pirate-radio-worker-1  Up"
        exit 0
        ;;

    # Service management
    *"up -d"*)
        echo "✔ Network pantry-pirate-radio_default Created"
        echo "✔ Container pantry-pirate-radio-db-1 Started"
        echo "✔ Container pantry-pirate-radio-cache-1 Started"
        echo "✔ Container pantry-pirate-radio-app-1 Started"
        if [[ "$*" == *"worker"* ]]; then
            echo "✔ Container pantry-pirate-radio-worker-1 Started"
        fi
        exit 0
        ;;

    *"down"*)
        echo "✔ Container pantry-pirate-radio-app-1 Stopped"
        echo "✔ Container pantry-pirate-radio-worker-1 Stopped"
        echo "✔ Container pantry-pirate-radio-db-1 Stopped"
        echo "✔ Container pantry-pirate-radio-cache-1 Stopped"
        echo "✔ Network pantry-pirate-radio_default Removed"
        exit 0
        ;;

    # Database checks
    *"exec -T db pg_isready"*)
        echo "localhost:5432 - accepting connections"
        exit 0
        ;;

    *"exec -T db psql"*"SELECT 1 FROM record_version"*)
        echo " ?column?"
        echo "----------"
        echo "        1"
        echo "(1 row)"
        exit 0
        ;;

    *"exec -T db psql"*"CREATE DATABASE"*)
        echo "CREATE DATABASE"
        exit 0
        ;;

    # Redis checks
    *"exec -T cache redis-cli ping"*)
        echo "PONG"
        exit 0
        ;;

    # Content store checks
    *"exec -T worker test -d /app/data/content_store"*)
        exit 0
        ;;

    *"exec -T worker test -f /app/data/content_store/content_store.db"*)
        exit 0
        ;;

    # Git checks
    *"exec -T haarrrvest-publisher test -d /app/data_repo"*)
        exit 0
        ;;

    *"exec -T haarrrvest-publisher git"*"config"*)
        echo "user.email=bot@pantrypirateradio.org"
        exit 0
        ;;

    # Scraper operations
    *"exec -T scraper python -m app.scraper --list"*)
        echo "Available scrapers:"
        echo "  - nyc_efap_programs"
        echo "  - food_bank_nyc"
        echo "  - hunter_college_nyc_food_pantries"
        echo "  - nj_snap_screener"
        echo "  - usda_food_access_research_atlas"
        echo "  - westchester_ny_food_resources"
        echo "  - feedingnys_org_find_food"
        echo "  - nyc_community_fridges"
        echo "  - findhelp_org"
        echo "  - ny_211_food"
        echo "  - food_rescue_us_agency_locator"
        echo "  - nomnom_food_map"
        exit 0
        ;;

    *"exec -T scraper python -m app.scraper"*)
        scraper_name=$(echo "$*" | grep -oE '[a-z_]+$')
        echo "Running scraper: $scraper_name"
        echo "Fetching data from source..."
        echo "Submitted 15 jobs to Redis queue"
        echo "Scraper completed successfully"
        exit 0
        ;;

    # Test scraper operations
    *"exec -T scraper python -m app.scraper.test_scrapers"*)
        if [[ "$*" == *"--all"* ]]; then
            echo "Testing all scrapers (dry run)..."
            echo "✓ nyc_efap_programs: 15 jobs would be submitted"
            echo "✓ food_bank_nyc: 8 jobs would be submitted"
            echo "✓ hunter_college_nyc_food_pantries: 23 jobs would be submitted"
            echo "All scrapers tested successfully"
        else
            scraper_name=$(echo "$*" | grep -oE '[a-z_]+$')
            echo "Testing scraper: $scraper_name (dry run)"
            echo "✓ Would submit 10 jobs to queue"
        fi
        exit 0
        ;;

    # Worker operations
    *"exec -T worker python -m app.claude_auth_manager status"*)
        echo "Claude authentication status: Valid"
        echo "Model: claude-3-opus-20240229"
        echo "Rate limit: 40 requests/minute"
        exit 0
        ;;

    # Reconciler operations
    *"exec -T reconciler python -m app.reconciler"*)
        echo "Starting reconciler..."
        echo "Processing job results from Redis..."
        echo "Processed 25 job results"
        echo "Created 10 new records, updated 15 existing records"
        exit 0
        ;;

    # Recorder operations
    *"exec -T recorder python -m app.recorder"*)
        echo "Starting recorder..."
        echo "Recording job results to JSON files..."
        echo "Saved 25 results to outputs/daily/2024-01-25/"
        echo "Updated latest symlink"
        exit 0
        ;;

    # Content store operations
    *"exec -T worker python -m app.content_store"*)
        if [[ "$*" == *"status"* ]]; then
            echo "Content Store Status:"
            echo "Path: /app/data/content_store"
            echo "Database: content_store.db (2.3 MB)"
            echo "Total entries: 1,234"
            echo "Storage used: 45.6 MB"
        elif [[ "$*" == *"report"* ]]; then
            echo "Content Store Report:"
            echo "Total unique content: 1,234"
            echo "Duplicate content avoided: 567"
            echo "Space saved: 23.4 MB"
        elif [[ "$*" == *"duplicates"* ]]; then
            echo "Top duplicate content:"
            echo "1. 'Food pantry hours' - 45 occurrences"
            echo "2. 'Emergency food assistance' - 38 occurrences"
        elif [[ "$*" == *"efficiency"* ]]; then
            echo "Storage efficiency: 68.3%"
            echo "Deduplication ratio: 1.46:1"
        fi
        exit 0
        ;;

    # HAARRRvest operations
    *"exec -T haarrrvest-publisher python -m app.haarrrvest_publisher.service --once"*)
        echo "HAARRRvest Publisher starting..."
        echo "Checking for new data..."
        echo "Found updates in outputs/daily/2024-01-25/"
        echo "Creating branch: data-update-2024-01-25"
        echo "Syncing 25 JSON files..."
        echo "Generating SQLite database..."
        echo "Creating pull request..."
        echo "PR created: https://github.com/example/haarrrvest/pull/123"
        exit 0
        ;;

    # Datasette operations
    *"exec -T datasette-exporter python -m app.datasette export"*)
        echo "Exporting PostgreSQL to SQLite..."
        echo "Connected to database"
        echo "Found 15 tables to export"
        echo "Exporting organization... 523 rows"
        echo "Exporting location... 1,234 rows"
        echo "Exporting service... 892 rows"
        echo "Creating views..."
        echo "Export complete: /data/pantry_pirate_radio.sqlite"
        exit 0
        ;;

    *"exec -T datasette-exporter test -f"*"latest.sqlite"*)
        exit 0
        ;;

    # Replay operations
    *"exec -T worker python -m app.replay"*)
        if [[ "$*" == *"--dry-run"* ]]; then
            echo "[DRY RUN] Replay operation"
        fi
        if [[ "$*" == *"--file"* ]]; then
            echo "Replaying single file..."
            echo "Successfully processed job: job_12345"
        elif [[ "$*" == *"--directory"* ]]; then
            echo "Replaying directory..."
            echo "Found 150 JSON files"
            echo "Processing: 150/150 files (100.0%)"
            echo "Successfully processed 148 files, 2 failed"
        fi
        exit 0
        ;;

    # Logs
    *"logs"*)
        if [[ "$*" == *"-f"* ]]; then
            echo "[2024-01-25 10:00:00] Service started"
            echo "[2024-01-25 10:00:01] Listening on port 8000"
            echo "[2024-01-25 10:00:02] Ready to accept connections"
            # Would continue forever, but exit for testing
        else
            echo "[2024-01-25 10:00:00] Service started"
            echo "[2024-01-25 10:00:01] Listening on port 8000"
            echo "[2024-01-25 10:00:02] Ready to accept connections"
            echo "[2024-01-25 10:01:00] Handled 10 requests"
        fi
        exit 0
        ;;

    # Build operations
    *"build"*)
        echo "Building pantry-pirate-radio-app..."
        echo "[+] Building 2.5s (15/15) FINISHED"
        echo " => [app 1/5] FROM docker.io/python:3.11"
        echo " => [app 2/5] WORKDIR /app"
        echo " => [app 3/5] COPY requirements.txt ."
        echo " => [app 4/5] RUN pip install -r requirements.txt"
        echo " => [app 5/5] COPY . ."
        echo " => exporting to image"
        echo " => => naming to docker.io/library/pantry-pirate-radio-app"
        exit 0
        ;;

    # Exec fallthrough for other commands
    *"exec -T"*)
        # Extract the command being executed
        service=$(echo "$*" | awk '{for(i=1;i<=NF;i++) if($i=="-T") print $(i+1)}')
        command=$(echo "$*" | sed "s/.*exec -T $service //")
        echo "Executing on $service: $command"
        exit 0
        ;;

    # Default case
    *)
        echo "Mock docker compose: Unhandled command: $*" >&2
        exit 1
        ;;
esac