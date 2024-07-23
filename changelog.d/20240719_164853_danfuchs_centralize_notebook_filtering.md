<!-- Delete the sections that don't apply -->

### Backwards-incompatible changes

- Remove `exclude_dirs` option from `NotebookRunner` options, which means it can no longer be set in the autostart config. `exclude_dirs` must be set in an in-repo `mobu.yaml` config file.
