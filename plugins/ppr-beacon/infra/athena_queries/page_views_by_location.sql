-- Top location pages by view count (last 30 days)
SELECT
  cs_uri_stem AS page,
  COUNT(*) AS views,
  COUNT(DISTINCT c_ip) AS unique_visitors
FROM cloudfront_logs
WHERE date >= current_date - INTERVAL '30' DAY
  AND sc_status = 200
  AND cs_uri_stem LIKE '/%/%/%'  -- state/city/location depth
  AND cs_uri_stem NOT LIKE '/static/%'
  AND x_edge_result_type != 'Error'
GROUP BY cs_uri_stem
ORDER BY views DESC
LIMIT 100;
