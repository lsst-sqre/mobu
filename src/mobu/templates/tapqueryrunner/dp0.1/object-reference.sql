SELECT '{{ query_id }}', 'object-reference', *
FROM dp01_dc2_catalogs.object AS o
JOIN dp01_dc2_catalogs.reference AS r
ON o.objectId = r.objectId
WHERE o.objectId = {{ object }}
