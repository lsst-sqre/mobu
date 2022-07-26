SELECT '{{ username }}', 'neighbor-near', o1.objectId AS id1, o2.objectId AS id2,
DISTANCE(POINT('ICRS', o1.coord_ra, o1.coord_dec), POINT('ICRS', o2.coord_ra, o2.coord_dec)) AS d
FROM dp02_dc2_catalogs.Object o1, dp02_dc2_catalogs.Object o2
WHERE CONTAINS(POINT('ICRS', o1.coord_ra, o1.coord_dec), CIRCLE('ICRS', {{ ra }}, {{ dec }}, {{ radius_near }}))=1
AND DISTANCE(POINT('ICRS', o1.coord_ra, o1.coord_dec), POINT('ICRS', o2.coord_ra, o2.coord_dec)) < 0.005
AND o1.objectId <> o2.objectId
