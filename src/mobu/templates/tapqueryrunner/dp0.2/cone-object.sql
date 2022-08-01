SELECT '{{ query_id }}', 'cone-object', *
FROM dp02_dc2_catalogs.Object
WHERE CONTAINS(POINT('ICRS', coord_ra, coord_dec), CIRCLE('ICRS', {{ ra }}, {{ dec }}, {{ radius }}))=1
