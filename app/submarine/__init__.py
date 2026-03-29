"""Scraper Submarine — post-reconciler pipeline stage.

Crawls food bank websites to fill missing data fields (hours, phone,
email, description) for locations that already exist in the database.
Uses crawl4ai for LLM-driven web content extraction.

Pipeline position:
    Reconciler → Submarine Queue → Submarine Worker → Reconciler Queue
"""
