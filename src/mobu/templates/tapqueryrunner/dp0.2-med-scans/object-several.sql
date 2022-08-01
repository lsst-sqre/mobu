SELECT '{{ query_id }}', 'object-several', *
FROM dp02_dc2_catalogs.Object
WHERE objectId IN ({{ objects }})
