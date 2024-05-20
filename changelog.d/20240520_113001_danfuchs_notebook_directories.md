<!-- Delete the sections that don't apply -->

### Backwards-incompatible changes

- NotebookRunner business now runs all notebooks in a repo, at tht root and in all subdirs recursively, by default.
- Add `exclude_dirs` option to NotebookRunner business to list directories in which notebooks will not be run.
