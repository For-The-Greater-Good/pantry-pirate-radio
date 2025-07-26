# Setting Up GitHub Pages for Interactive Data Access

This guide walks through enabling GitHub Pages on your data repository to provide interactive access to the SQLite database.

## Prerequisites

- Data repository created (e.g., `HAARRRvest`)
- SQLite file being synced to `sqlite/pantry_pirate_radio.sqlite`
- Admin access to the repository

## Step 1: Enable GitHub Pages

1. Go to your data repository on GitHub
2. Navigate to **Settings** → **Pages**
3. Under **Source**, select **Deploy from a branch**
4. Choose **main** branch and **/ (root)** folder
5. Click **Save**

## Step 2: Verify Files

After running the publish pipeline, verify these files exist in your data repository:

- `index.html` - The interactive Datasette-Lite interface
- `explore.html` - Redirect page for backwards compatibility
- `sqlite/pantry_pirate_radio.sqlite` - Your SQLite database

## Step 3: Access Your Data

Once GitHub Pages is enabled and the pipeline has run:

1. Visit: `https://[your-username].github.io/[repo-name]/`
   - Example: `https://for-the-greater-good.github.io/HAARRRvest/`

2. The page will load Datasette-Lite with your SQLite database

3. You can now:
   - Browse tables interactively
   - Run SQL queries
   - Export data in various formats
   - Create visualizations

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

1. Check GitHub Pages is enabled in settings
2. Wait 10 minutes for initial deployment
3. Check for build errors in Actions tab

### Database Not Loading

1. Verify SQLite file exists at correct path
2. Check file size (should be under 100MB for Datasette-Lite)
3. Ensure file is accessible via raw.githubusercontent.com

### Plugins Not Working

Some Datasette plugins may not work in Datasette-Lite. The template includes:
- datasette-cluster-map (for map visualizations)
- datasette-vega (for charts)

## Customization

### Modify the Interface

Edit `index.html` in your data repository to:

- Change colors/styling
- Add custom links
- Modify the header
- Add analytics

### Add Query Examples

Add a section to your README.md with useful queries:

```markdown
## Example Queries

### Find food pantries in NYC
```sql
SELECT name, address_1, city, latitude, longitude
FROM locations
WHERE city = 'New York'
  AND state_province = 'NY'
LIMIT 20;
```

### Organizations with most locations
```sql
SELECT o.name, COUNT(l.id) as location_count
FROM organizations o
JOIN locations l ON o.id = l.organization_id
GROUP BY o.id, o.name
ORDER BY location_count DESC
LIMIT 10;
```
```

## Security Considerations

- The SQLite file is publicly accessible
- Don't include sensitive data
- Consider data privacy regulations
- Use `.gitignore` for local-only data

## Performance Tips

- Keep SQLite file under 100MB for best performance
- Create indexes for commonly queried columns
- Use views for complex queries
- Consider splitting very large datasets

## Alternative Hosting

If GitHub Pages doesn't meet your needs:

1. **Netlify**: Drag and drop deployment
2. **Vercel**: Serverless functions support
3. **Cloudflare Pages**: Global CDN
4. **Self-hosted**: Use regular Datasette

## Next Steps

1. Share the link with your community
2. Add example queries to help users
3. Create visualizations with Observable
4. Embed the interface in other websites