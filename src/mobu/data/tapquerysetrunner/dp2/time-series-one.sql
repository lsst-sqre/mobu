SELECT '{{ query_id }}', 'time-series-one', *
FROM dp2.Object AS o
JOIN dp2.ForcedSource AS fs
ON o.objectId = fs.objectId
WHERE o.objectId = {{ object }}
