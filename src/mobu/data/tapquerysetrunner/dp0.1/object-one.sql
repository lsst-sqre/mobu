SELECT '{{ query_id }}', 'object-one', *
FROM dp01_dc2_catalogs.object
WHERE objectId = {{ object }}
