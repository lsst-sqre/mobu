<!-- Delete the sections that don't apply -->

### Backwards-incompatible changes

- All app config, including autostart config (and excluding secrets, which still come from env vars) now comes from a single YAML file, provisioned by a single `ConfigMap` in Phalanx.
