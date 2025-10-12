Helios ECPro Ventilation 4.0.0

- Major release: UX/docs polish and cleanups
  - Climate/Fan entity pictures standardized to the integration endpoint /api/helios_pro_ventilation/image.png (public; serves config/www image if present or falls back to packaged/transparent).
  - README now includes ready-to-copy Lovelace YAML for Climate/Fan (Picture Entity, Tile) and action buttons.
  - Duplicate binary sensor issue resolved; ilter_warning remains diagnostic; uto_mode provided only via the binary_sensor platform.
  - Date/time fix finalized: Var_07/Var_08 decoding, startup reads and 10minute cadence are in place and tested.
  - Housekeeping: removed TODO.md (tracked via repository issues/notes).
