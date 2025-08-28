# Setting Up GitHub Pages for Interactive Data Access

This guide walks through enabling GitHub Pages on your data repository to provide interactive access to the SQLite database.

## Prerequisites

- HAARRRvest repository created and configured
- Pantry Pirate Radio services running with `./bouy up`
- GitHub Personal Access Token with `repo` scope
- Admin access to the HAARRRvest repository
- `PUBLISHER_PUSH_ENABLED=true` set in `.env` (for production)

## Step 1: Enable GitHub Pages

1. Go to your data repository on GitHub
2. Navigate to **Settings** → **Pages**
3. Under **Source**, select **Deploy from a branch**
4. Choose **main** branch and **/ (root)** folder
5. Click **Save**

## Step 2: Run the Publishing Pipeline

```bash
# Ensure services are running
./bouy up

# Run scrapers to generate data
./bouy scraper --list  # See available scrapers
./bouy scraper nyc_efap_programs  # Run a specific scraper

# Monitor the pipeline
./bouy logs worker     # Watch LLM processing
./bouy logs recorder   # Watch data recording
./bouy haarrrvest logs # Watch publishing

# Manually trigger publishing if needed
./bouy haarrrvest run
```

After the pipeline completes, verify these files exist in HAARRRvest:

- `index.html` - The interactive Datasette-Lite interface
- `sqlite/pantry_pirate_radio.sqlite` - Your SQLite database
- `daily/` - Daily JSON data archives
- `sql_dumps/latest.sql` - Latest PostgreSQL dump
- `data/` - Map visualization data

## Step 3: Access Your Data

Once GitHub Pages is enabled and the pipeline has run:

### Public Access via GitHub Pages
1. Visit: `https://[your-username].github.io/[repo-name]/`
   - Example: `https://datasette.for-the-gg.org`

2. The page will load Datasette-Lite with your SQLite database

3. You can now:
   - Browse tables interactively
   - Run SQL queries
   - Export data in various formats (CSV, JSON)
   - Create visualizations

### Local Development Access
```bash
# Via FastAPI (for API access)
http://localhost:8000/docs  # Interactive API documentation
http://localhost:8000/api/v1/locations  # Direct API endpoints

# Via Datasette (production mode only)
./bouy up --prod
http://localhost:8001  # Datasette UI
```

## Step 4: Custom Domain (Optional)

To use a custom domain:

1. In repository **Settings** → **Pages**
2. Under **Custom domain**, enter your domain
3. Create a `CNAME` file in the repository root with your domain

## Features Available

The interactive interface provides:

- **Full SQL Query Interface**: Write and execute any SQL query
- **Table Browser**: Click through tables and records
- **Data Export**: Download results as CSV, JSON
- **Faceted Search**: Filter data interactively
- **Map Visualizations**: If datasette-cluster-map plugin loads
- **Charts**: If datasette-vega plugin loads

## Troubleshooting

### Page Not Loading

1. Check GitHub Pages is enabled: Settings → Pages
2. Verify repository is public (required for free GitHub Pages)
3. Wait 10-15 minutes for initial deployment
4. Check Actions tab for deployment errors
5. Verify `index.html` exists in repository root:
   ```bash
   ./bouy exec app ls -la /data-repo/index.html
   ```

### Database Not Loading

1. Verify SQLite file was created:
   ```bash
   ./bouy exec app ls -la /data-repo/sqlite/
   ```
2. Check file size (should be under 100MB for Datasette-Lite):
   ```bash
   ./bouy exec app du -h /data-repo/sqlite/*.sqlite
   ```
3. Ensure file is accessible via:
   ```
   https://raw.githubusercontent.com/[org]/HAARRRvest/main/sqlite/pantry_pirate_radio.sqlite
   ```
4. Check publisher logs for export errors:
   ```bash
   ./bouy haarrrvest logs | grep -i sqlite
   ```

### Plugins Not Working

Some Datasette plugins may not work in Datasette-Lite. The template includes:
- datasette-cluster-map (for map visualizations)
- datasette-vega (for charts)

## Customization

### Modify the Interface

The HAARRRvest publisher automatically generates `index.html`. To customize:

1. Fork the HAARRRvest repository
2. Edit `index.html` to:
   - Change colors/styling
   - Add custom links
   - Modify the header
   - Add analytics
3. Commit changes
4. The publisher will preserve your customizations

### Environment Configuration

Customize publisher behavior via `.env`:

```bash
# Publishing frequency
PUBLISHER_CHECK_INTERVAL=300  # Seconds between checks

# Data retention
DAYS_TO_SYNC=7  # Days of data to sync

# SQL dump settings
SQL_DUMP_MIN_RECORDS=100  # Minimum records for dump
SQL_DUMP_RATCHET_PERCENTAGE=0.9  # Safety threshold
```

### Add Query Examples

The HAARRRvest publisher auto-generates a README with statistics. Add custom queries:

```markdown
## Example Queries

### Find food pantries near a location
```sql
-- Find services within 5 miles of a point
SELECT 
    l.name,
    l.address_1,
    l.city,
    l.latitude,
    l.longitude,
    s.name as service_name,
    s.description
FROM locations l
JOIN service_at_location sal ON l.id = sal.location_id
JOIN services s ON sal.service_id = s.id
WHERE l.latitude BETWEEN 40.7 AND 40.8
  AND l.longitude BETWEEN -74.1 AND -74.0
LIMIT 20;
```

### Organizations with most locations
```sql
SELECT 
    o.name,
    COUNT(DISTINCT l.id) as location_count,
    COUNT(DISTINCT s.id) as service_count
FROM organizations o
LEFT JOIN locations l ON o.id = l.organization_id
LEFT JOIN services s ON o.id = s.organization_id
GROUP BY o.id, o.name
ORDER BY location_count DESC
LIMIT 10;
```

### Recent data updates
```sql
SELECT 
    DATE(created_at) as date,
    COUNT(*) as records_added
FROM locations
WHERE created_at > date('now', '-7 days')
GROUP BY DATE(created_at)
ORDER BY date DESC;
```
```

## Security Considerations

- The SQLite file is publicly accessible on GitHub Pages
- Only public food resource data should be included
- Personal information must never be collected or published
- Use environment variables for sensitive configuration:
  ```bash
  DATA_REPO_TOKEN=xxx  # Never commit tokens
  PUBLISHER_PUSH_ENABLED=false  # Default to safe mode
  ```
- Review data before enabling push:
  ```bash
  ./bouy exec app sqlite3 /data-repo/sqlite/pantry_pirate_radio.sqlite ".tables"
  ```

## Performance Tips

- Keep SQLite file under 100MB for Datasette-Lite performance
- The publisher automatically creates indexes on key columns
- Monitor database size:
  ```bash
  ./bouy exec app du -h /data-repo/sqlite/*.sqlite
  ```
- Use SQL dumps for faster initialization:
  ```bash
  ./bouy exec app ls -lh /data-repo/sql_dumps/latest.sql
  ```
- Configure data retention:
  ```bash
  DAYS_TO_SYNC=7  # Reduce for smaller databases
  ```

## Alternative Hosting

If GitHub Pages doesn't meet your needs:

1. **Netlify**: Drag and drop deployment
2. **Vercel**: Serverless functions support
3. **Cloudflare Pages**: Global CDN
4. **Self-hosted**: Use regular Datasette

## Next Steps

1. **Monitor Publishing**: Check logs regularly
   ```bash
   ./bouy haarrrvest logs
   ```

2. **Add More Data Sources**: Run additional scrapers
   ```bash
   ./bouy scraper --list
   ./bouy scraper --all  # Run all scrapers
   ```

3. **Share with Community**: 
   - Public data: `https://datasette.for-the-gg.org`
   - API endpoint: Document your API URL for developers
   - Embed Datasette-Lite in other sites using iframes

4. **Track Usage**: Monitor GitHub Insights and API metrics
   ```bash
   curl http://localhost:8000/metrics  # Prometheus metrics
   ```