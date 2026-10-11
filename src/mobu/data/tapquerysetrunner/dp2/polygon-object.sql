SELECT '{{ query_id }}', 'polygon-object', *
FROM dp2.Object
WHERE CONTAINS(POINT('ICRS', coord_ra, coord_dec), POLYGON('ICRS', {{ polygon }}))=1
