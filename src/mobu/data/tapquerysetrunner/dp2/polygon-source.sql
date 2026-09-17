SELECT '{{ query_id }}', 'polygon-source', *
FROM dp2.Source
WHERE CONTAINS(POINT('ICRS', coord_ra, coord_dec), POLYGON('ICRS', {{ polygon }}))=1
