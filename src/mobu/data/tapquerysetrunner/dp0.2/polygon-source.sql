SELECT '{{ query_id }}', 'polygon-source', *
FROM dp02_dc2_catalogs.Source
WHERE CONTAINS(POINT('ICRS', coord_ra, coord_dec), POLYGON('ICRS', {{ polygon }}))=1
