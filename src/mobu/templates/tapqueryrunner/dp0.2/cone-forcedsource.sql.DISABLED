SELECT '{{ query_id }}', 'cone-forcedsource', *
FROM dp02_dc2_catalogs.ForcedSource
WHERE CONTAINS(POINT('ICRS', coord_ra, coord_dec), CIRCLE('ICRS', {{ ra }}, {{ dec }}, {{ radius }}))=1
