SELECT '{{ query_id }}', 'time-series-one', *
FROM dp02_dc2_catalogs.Object AS o
JOIN dp02_dc2_catalogs.ForcedSource AS fs
ON o.objectId = fs.objectId
WHERE o.objectId = {{ object }}
