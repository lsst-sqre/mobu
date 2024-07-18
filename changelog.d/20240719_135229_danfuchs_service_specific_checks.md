<!-- Delete the sections that don't apply -->

### Backwards-incompatible changes

- `exclude_dirs` from an in-repo `mobu.yaml` config file will overrided `exclude_dirs` in the Phalanx autostart config.

### New features

- `NotebookRunner` business will skip notebooks in environments that do not have the services required for them to run. Required services ban be declared by adding [metadata](https://ipython.readthedocs.io/en/3.x/notebook/nbformat.html#metadata) to a notebook.
