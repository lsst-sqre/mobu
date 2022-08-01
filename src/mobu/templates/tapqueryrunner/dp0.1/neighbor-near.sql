SELECT '{{ query_id }}', 'neighbor-near', o1.objectId AS id1, o2.objectId AS id2,
DISTANCE(POINT('ICRS', o1.ra, o1.dec), POINT('ICRS', o2.ra, o2.dec)) AS d
FROM dp01_dc2_catalogs.object o1, dp01_dc2_catalogs.object o2
WHERE CONTAINS(POINT('ICRS', o1.ra, o1.dec), CIRCLE('ICRS', {{ ra }}, {{ dec }}, {{ radius_near }}))=1
AND DISTANCE(POINT('ICRS', o1.ra, o1.dec), POINT('ICRS', o2.ra, o2.dec)) < 0.005
AND o1.objectId <> o2.objectId
