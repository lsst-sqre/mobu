SELECT TOP 12 '{{ query_id }}', 'scan-top',
objectId, ra, dec, extendedness, mag_r, magerr_r, good
FROM dp01_dc2_catalogs.object
WHERE extendedness = 0 AND mag_r < 24
ORDER by mag_r DESC
