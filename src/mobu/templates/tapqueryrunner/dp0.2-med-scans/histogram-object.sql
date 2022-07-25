SELECT '{{ username }}', 'histogram-object',
COUNT(*), FLOOR(-2.5 * LOG10(r_cModelFlux) + 31.4) as abMag
FROM dp02_dc2_catalogs.Object
WHERE refExtendedness = 0 and r_cModelFlux > 0.0
GROUP BY abMag
ORDER BY abMag
