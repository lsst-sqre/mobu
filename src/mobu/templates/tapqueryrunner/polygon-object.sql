SELECT 'monkey', *
FROM dp01_dc2_catalogs.object
WHERE CONTAINS(POINT('ICRS', ra, dec), POLYGON('ICRS', {{ polygon }}))=1
