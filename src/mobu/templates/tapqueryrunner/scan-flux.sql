SELECT 'monkey', objectId, coord_ra, coord_dec, i_base_PsfFlux_instFlux
FROM dp01_dc2_catalogs.forced_photometry
WHERE i_base_PsfFlux_instFlux BETWEEN {{ min_flux }} AND {{ max_flux }}
