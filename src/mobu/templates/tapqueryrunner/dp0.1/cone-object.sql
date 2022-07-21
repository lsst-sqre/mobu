SELECT 'monkey', 'cone-object', *
FROM dp01_dc2_catalogs.object
WHERE CONTAINS(POINT('ICRS', ra, dec), CIRCLE('ICRS', {{ ra }}, {{ dec }}, {{ radius }}))=1
