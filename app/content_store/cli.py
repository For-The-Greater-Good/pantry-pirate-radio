#!/usr/bin/env python3
"""CLI commands for content store."""

import click


@click.group()
def cli():
    """Content store management commands."""
    pass


@cli.command()
@click.option("--host", default="127.0.0.1", help="Host to bind to")
@click.option("--port", default=5050, type=int, help="Port to bind to")
def dashboard(host, port):
    """Run the content store dashboard."""
    from app.content_store.dashboard import app

    print(f"Starting Content Store Dashboard on http://{host}:{port}")
    print("Access the dashboard at http://localhost:5050 from your host machine")
    app.run(host=host, port=port, debug=False)


@cli.command()
def status():
    """Show content store status."""
    from pathlib import Path
    from app.content_store import ContentStore

    store = ContentStore(Path("/data-repo"))
    stats = store.get_statistics()

    print("Content Store Status:")
    print(f"  Total entries: {stats['total_content']}")
    print(f"  Completed: {stats['processed_content']}")
    print(f"  Pending: {stats['pending_content']}")
    print(f"  Store size: {stats['store_size_bytes'] / 1024 / 1024:.2f} MB")


@cli.command()
@click.argument("content_hash")
def inspect(content_hash):
    """Inspect a specific content hash."""
    import json
    from pathlib import Path
    from app.content_store import ContentStore

    store = ContentStore(Path("/data-repo"))

    try:
        store._validate_hash(content_hash)
    except ValueError as e:
        print(f"Error: {e}")
        return

    # Check if content exists
    if not store.has_content(content_hash):
        print(f"Content hash {content_hash} not found in store")
        return

    print(f"Content Hash: {content_hash}")

    # Show content
    content_path = store._get_content_path(content_hash)
    if content_path.exists():
        data = json.loads(content_path.read_text())
        print("\nContent:")
        print(f"  Stored at: {data.get('timestamp', 'Unknown')}")
        print(f"  Metadata: {json.dumps(data.get('metadata', {}), indent=2)}")
        print(f"  Content preview: {data.get('content', '')[:200]}...")

    # Show result
    result = store.get_result(content_hash)
    if result:
        print("\nResult:")
        print("  Status: Completed")
        print(f"  Result preview: {result[:200]}...")
    else:
        print("\nResult: Not yet processed")
        job_id = store.get_job_id(content_hash)
        if job_id:
            print(f"  Job ID: {job_id}")


if __name__ == "__main__":
    cli()
