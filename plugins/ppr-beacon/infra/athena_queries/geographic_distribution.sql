-- Views by CloudFront edge location (proxy for visitor geography, last 30 days)
SELECT
  x_edge_location AS edge_location,
  COUNT(*) AS requests,
  COUNT(DISTINCT c_ip) AS unique_visitors
FROM cloudfront_logs
WHERE date >= current_date - INTERVAL '30' DAY
  AND sc_status = 200
  AND cs_uri_stem NOT LIKE '/static/%'
GROUP BY x_edge_location
ORDER BY requests DESC;
