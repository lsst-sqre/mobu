SELECT 'monkey', 'histogram-forcedsource',
COUNT(*), FLOOR(-2.5 * LOG10(psfFlux) + 31.4) as abMag
FROM dp02_dc2_catalogs.ForcedSource
WHERE psfFlux > 0.0
GROUP BY abMag
ORDER BY abMag
