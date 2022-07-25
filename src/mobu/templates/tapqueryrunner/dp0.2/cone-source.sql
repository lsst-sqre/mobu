SELECT '{{ username }}', 'cone-source', *
FROM dp02_dc2_catalogs.Source
WHERE CONTAINS(POINT('ICRS', coord_ra, coord_dec), CIRCLE('ICRS', {{ ra }}, {{ dec }}, {{ radius }}))=1
