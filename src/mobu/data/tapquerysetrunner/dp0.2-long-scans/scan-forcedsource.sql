SELECT '{{ query_id }}', 'scan-forcedsource',
objectId, coord_ra, coord_dec, psfFlux
FROM dp02_dc2_catalogs.ForcedSource
WHERE psfFlux BETWEEN {{ min_flux }} AND {{ max_flux }}
