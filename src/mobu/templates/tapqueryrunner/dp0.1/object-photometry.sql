SELECT '{{ username }}', 'object-photometry', *
FROM dp01_dc2_catalogs.object AS o
JOIN dp01_dc2_catalogs.forced_photometry AS fp
ON o.objectId = fp.objectId
WHERE o.objectId IN ({{ objects }})
