SELECT '{{ username }}', 'cone-photometry', *
FROM dp01_dc2_catalogs.forced_photometry
WHERE CONTAINS(POINT('ICRS', coord_ra, coord_dec), CIRCLE('ICRS', {{ ra }}, {{ dec }}, {{ radius }}))=1
