SELECT '{{ query_id }}', 'cone-source', *
FROM dp2.Source
WHERE CONTAINS(POINT('ICRS', coord_ra, coord_dec), CIRCLE('ICRS', {{ ra }}, {{ dec }}, {{ radius }}))=1
