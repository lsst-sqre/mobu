SELECT TOP 12 'monkey', 'scan-object-top',
objectId, coord_ra, coord_dec, refExtendedness, r_cModelFlux, r_cModelFluxErr
FROM dp02_dc2_catalogs.Object
WHERE refExtendedness = 0 AND r_cModelFlux < 912.0
ORDER by r_cModelFlux DESC
