SELECT COUNT(*), FLOOR(object.mag_r) as BIN
FROM dp01_dc2_catalogs.object AS object
JOIN dp01_dc2_catalogs.truth_match AS truth
ON object.objectId = truth.match_objectId
WHERE is_good_match = 1 AND truth_type = 2 AND object.mag_r IS NOT NULL AND extendedness = 0
GROUP BY BIN
ORDER BY BIN
