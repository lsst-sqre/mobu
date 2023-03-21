SELECT '{{ query_id }}', 'polygon-object', *
FROM dp02_dc2_catalogs.Object
WHERE CONTAINS(POINT('ICRS', coord_ra, coord_dec), POLYGON('ICRS', {{ polygon }}))=1
