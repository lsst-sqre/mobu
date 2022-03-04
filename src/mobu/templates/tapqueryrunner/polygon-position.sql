SELECT 'monkey', *
FROM dp01_dc2_catalogs.position
WHERE CONTAINS(POINT('ICRS', coord_ra, coord_dec), POLYGON('ICRS', {{ polygon }}))=1
