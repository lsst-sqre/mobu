SELECT 'monkey', 'time-series-several', *
FROM dp02_dc2_catalogs.Object AS o
JOIN dp02_dc2_catalogs.ForcedSource AS fs
ON o.objectId = fs.objectId
WHERE o.objectId IN ({{ objects }})
