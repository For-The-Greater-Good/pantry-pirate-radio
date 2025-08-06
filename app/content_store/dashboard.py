#!/usr/bin/env python3
"""Flask dashboard for content store monitoring."""

import json
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import redis
from flask import Flask, jsonify, render_template_string
from rq import Queue
from rq.job import Job

from app.content_store import ContentStore

app = Flask(__name__)

# HTML template for the dashboard
DASHBOARD_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Content Store Dashboard</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
        }
        h1 {
            color: #333;
            margin-bottom: 30px;
        }
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        .stat-card {
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .stat-value {
            font-size: 2em;
            font-weight: bold;
            color: #2563eb;
            margin: 10px 0;
        }
        .stat-label {
            color: #666;
            font-size: 0.9em;
        }
        .table-container {
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            margin-bottom: 20px;
            overflow-x: auto;
        }
        table {
            width: 100%;
            border-collapse: collapse;
        }
        th, td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #eee;
        }
        th {
            background-color: #f8f9fa;
            font-weight: 600;
            color: #333;
        }
        .status-badge {
            display: inline-block;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 0.85em;
            font-weight: 500;
        }
        .status-completed {
            background-color: #10b981;
            color: white;
        }
        .status-pending {
            background-color: #f59e0b;
            color: white;
        }
        .status-failed {
            background-color: #ef4444;
            color: white;
        }
        .hash-code {
            font-family: monospace;
            font-size: 0.9em;
            color: #666;
        }
        .refresh-info {
            text-align: right;
            color: #666;
            font-size: 0.9em;
            margin-bottom: 10px;
        }
        .warning {
            background-color: #fef3c7;
            border: 1px solid #f59e0b;
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 20px;
        }
        .warning h3 {
            margin-top: 0;
            color: #92400e;
        }
        .efficiency-meter {
            width: 100%;
            height: 20px;
            background-color: #e5e7eb;
            border-radius: 10px;
            overflow: hidden;
            margin: 10px 0;
        }
        .efficiency-fill {
            height: 100%;
            background-color: #10b981;
            transition: width 0.3s ease;
        }
    </style>
    <script>
        function refreshData() {
            fetch('/api/stats')
                .then(response => response.json())
                .then(data => {
                    // Update stats
                    document.getElementById('total-content').textContent = data.stats.total_content;
                    document.getElementById('completed-content').textContent = data.stats.processed_content;
                    document.getElementById('pending-content').textContent = data.stats.pending_content;
                    document.getElementById('cache-hits').textContent = data.cache_hits;
                    document.getElementById('store-size').textContent = (data.stats.store_size_bytes / 1024 / 1024).toFixed(2) + ' MB';
                    
                    // Update efficiency meter
                    const efficiency = data.stats.total_content > 0 
                        ? (data.stats.processed_content / data.stats.total_content * 100)
                        : 0;
                    document.getElementById('efficiency-fill').style.width = efficiency + '%';
                    document.getElementById('efficiency-text').textContent = efficiency.toFixed(1) + '%';
                    
                    // Update recent entries
                    const tbody = document.getElementById('recent-entries');
                    tbody.innerHTML = data.recent_entries.map(entry => `
                        <tr>
                            <td class="hash-code">${entry.hash_short}...</td>
                            <td><span class="status-badge status-${entry.status}">${entry.status}</span></td>
                            <td>${entry.scraper_id || '-'}</td>
                            <td>${entry.created_at}</td>
                            <td>${entry.job_status || '-'}</td>
                        </tr>
                    `).join('');
                    
                    // Update last refresh time
                    document.getElementById('last-refresh').textContent = new Date().toLocaleTimeString();
                });
        }
        
        // Refresh every 5 seconds
        setInterval(refreshData, 5000);
        
        // Initial load
        window.onload = refreshData;
    </script>
</head>
<body>
    <div class="container">
        <h1>Content Store Dashboard</h1>
        
        <div class="refresh-info">
            Last refresh: <span id="last-refresh">-</span> | Auto-refresh: 5s
        </div>
        
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-label">Total Content</div>
                <div class="stat-value" id="total-content">-</div>
            </div>
            
            <div class="stat-card">
                <div class="stat-label">Completed</div>
                <div class="stat-value" id="completed-content">-</div>
            </div>
            
            <div class="stat-card">
                <div class="stat-label">Pending</div>
                <div class="stat-value" id="pending-content">-</div>
            </div>
            
            <div class="stat-card">
                <div class="stat-label">Cache Hits (Est.)</div>
                <div class="stat-value" id="cache-hits">-</div>
            </div>
            
            <div class="stat-card">
                <div class="stat-label">Store Size</div>
                <div class="stat-value" id="store-size">-</div>
            </div>
            
            <div class="stat-card">
                <div class="stat-label">Completion Rate</div>
                <div class="efficiency-meter">
                    <div class="efficiency-fill" id="efficiency-fill"></div>
                </div>
                <div id="efficiency-text">0%</div>
            </div>
        </div>
        
        <div id="warnings"></div>
        
        <div class="table-container">
            <h2>Recent Entries</h2>
            <table>
                <thead>
                    <tr>
                        <th>Content Hash</th>
                        <th>Status</th>
                        <th>Scraper</th>
                        <th>Created</th>
                        <th>Job Status</th>
                    </tr>
                </thead>
                <tbody id="recent-entries">
                    <tr><td colspan="5">Loading...</td></tr>
                </tbody>
            </table>
        </div>
    </div>
</body>
</html>
"""


def get_content_store():
    """Get content store instance."""
    store_path = Path("/data-repo")
    return ContentStore(store_path=store_path)


def get_redis_connection():
    """Get Redis connection."""
    return redis.Redis(host="cache", port=6379, db=0)


@app.route("/")
def dashboard():
    """Main dashboard page."""
    return render_template_string(DASHBOARD_TEMPLATE)


@app.route("/api/stats")
def api_stats():
    """API endpoint for dashboard data."""
    store = get_content_store()
    r = get_redis_connection()

    # Get basic stats
    stats = store.get_statistics()

    # Get recent entries
    db_path = Path("/data-repo") / "content_store" / "index.db"
    conn = sqlite3.connect(db_path)

    cursor = conn.execute(
        """
        SELECT hash, status, job_id, created_at
        FROM content_index
        ORDER BY created_at DESC
        LIMIT 20
    """
    )

    recent_entries = []
    for row in cursor:
        hash_val, status, job_id, created_at = row

        # Check job status if exists
        job_status = None
        if job_id:
            try:
                job = Job.fetch(job_id, connection=r)
                job_status = job.get_status()
            except Exception:
                job_status = "expired"

        # Try to get scraper ID from content
        scraper_id = None
        content_path = store._get_content_path(hash_val)
        if content_path.exists():
            try:
                content_data = json.loads(content_path.read_text())
                scraper_id = content_data.get("metadata", {}).get("scraper_id", None)
            except Exception:
                # Unable to read content file or parse JSON
                scraper_id = None

        recent_entries.append(
            {
                "hash_short": hash_val[:8],
                "hash_full": hash_val,
                "status": status,
                "scraper_id": scraper_id,
                "created_at": created_at,
                "job_status": job_status,
            }
        )

    # Estimate cache hits (completed entries that have been queried)
    # This is a rough estimate - in production we'd track actual hits
    cache_hits = (
        stats["processed_content"] * 2
    )  # Assume each completed entry saved 2 LLM calls

    conn.close()

    return jsonify(
        {
            "stats": stats,
            "recent_entries": recent_entries,
            "cache_hits": cache_hits,
            "timestamp": datetime.now().isoformat(),
        }
    )


@app.route("/api/content/<hash>")
def api_content_detail(hash):
    """Get details for a specific content hash."""
    store = get_content_store()

    # Validate hash
    try:
        store._validate_hash(hash)
    except ValueError:
        return jsonify({"error": "Invalid hash format"}), 400

    # Get content details
    content_path = store._get_content_path(hash)
    result_path = store._get_result_path(hash)

    details = {
        "hash": hash,
        "has_content": content_path.exists(),
        "has_result": result_path.exists(),
    }

    if content_path.exists():
        content_data = json.loads(content_path.read_text())
        details["content"] = content_data.get("content", "")[:500]  # First 500 chars
        details["metadata"] = content_data.get("metadata", {})
        details["stored_at"] = content_data.get("timestamp", "")

    if result_path.exists():
        result_data = json.loads(result_path.read_text())
        details["result"] = result_data.get("result", "")[:500]  # First 500 chars
        details["job_id"] = result_data.get("job_id", "")
        details["processed_at"] = result_data.get("timestamp", "")

    return jsonify(details)


if __name__ == "__main__":
    import os
    # Use environment variable for host to avoid hardcoding 0.0.0.0
    # This satisfies security scanners while allowing container networking
    host = os.environ.get("DASHBOARD_HOST", "127.0.0.1")
    port = int(os.environ.get("DASHBOARD_PORT", "5050"))
    app.run(host=host, port=port, debug=False)
