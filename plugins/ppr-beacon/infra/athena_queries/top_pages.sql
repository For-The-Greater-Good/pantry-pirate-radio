-- Top 100 pages by total views (last 30 days)
SELECT
  cs_uri_stem AS page,
  COUNT(*) AS views,
  ROUND(AVG(time_taken), 3) AS avg_latency_sec,
  COUNT(DISTINCT c_ip) AS unique_visitors
FROM cloudfront_logs
WHERE date >= current_date - INTERVAL '30' DAY
  AND sc_status = 200
  AND cs_uri_stem NOT LIKE '/static/%'
  AND cs_uri_stem != '/robots.txt'
  AND cs_uri_stem != '/sitemap.xml'
GROUP BY cs_uri_stem
ORDER BY views DESC
LIMIT 100;
