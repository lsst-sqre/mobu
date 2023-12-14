SELECT '{{ query_id }}', 'scan-magnitude',
objectId, object.ra, object.dec, extendedness, object.mag_r,
object.magerr_r, good
FROM dp01_dc2_catalogs.object AS object
JOIN dp01_dc2_catalogs.truth_match AS truth
ON object.objectId = truth.match_objectId
WHERE extendedness = 0 AND is_good_match = 1 AND truth_type = 2
AND object.mag_r BETWEEN {{ min_mag }} AND {{ max_mag }}
