SELECT '{{ query_id }}', 'scan-object',
objectId, coord_ra, coord_dec, refExtendedness, r_cModelFlux, r_cModelFluxErr
FROM dp02_dc2_catalogs.Object
WHERE refExtendedness = 0 AND r_cModelFlux BETWEEN {{ min_flux }} AND {{ max_flux }}
