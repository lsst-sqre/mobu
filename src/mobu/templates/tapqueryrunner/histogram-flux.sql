SELECT 'monkey', 'histogram-flux',
COUNT(*), FLOOR(LOG10(i_base_PsfFlux_instFlux)) as BIN
FROM dp01_dc2_catalogs.forced_photometry
GROUP BY BIN
ORDER BY BIN
