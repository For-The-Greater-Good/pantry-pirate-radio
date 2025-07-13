SELECT
  t.table_name,
  t.record_count,
  COALESCE(v.version_count, 0) as version_count
FROM (
  SELECT 'organization' as table_name, COUNT(*) as record_count FROM organization
  UNION ALL
  SELECT 'service', COUNT(*) FROM service
  UNION ALL
  SELECT 'location', COUNT(*) FROM location
  UNION ALL
  SELECT 'service_at_location', COUNT(*) FROM service_at_location
) t
LEFT JOIN (
  SELECT record_type, COUNT(*) as version_count
  FROM record_version
  GROUP BY record_type
) v ON v.record_type = t.table_name
ORDER BY t.table_name;