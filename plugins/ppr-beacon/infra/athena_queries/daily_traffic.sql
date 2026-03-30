-- Daily page views and unique visitors (last 90 days)
SELECT
  date,
  COUNT(*) AS total_requests,
  COUNT(CASE WHEN sc_status = 200 THEN 1 END) AS page_views,
  COUNT(DISTINCT c_ip) AS unique_visitors,
  COUNT(CASE WHEN cs_user_agent LIKE '%bot%' OR cs_user_agent LIKE '%crawl%' OR cs_user_agent LIKE '%spider%' THEN 1 END) AS bot_requests
FROM cloudfront_logs
WHERE date >= current_date - INTERVAL '90' DAY
  AND cs_uri_stem NOT LIKE '/static/%'
GROUP BY date
ORDER BY date DESC;
