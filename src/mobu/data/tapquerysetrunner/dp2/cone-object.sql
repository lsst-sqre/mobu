SELECT '{{ query_id }}', 'cone-object', *
FROM dp2.Object
WHERE CONTAINS(POINT('ICRS', coord_ra, coord_dec), CIRCLE('ICRS', {{ ra }}, {{ dec }}, {{ radius }}))=1
