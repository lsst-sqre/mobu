<!-- Delete the sections that don't apply -->

### Backwards-incompatible changes

- GitHub CI and refresh app config are now each a separate, all-or-nothing set of config that comes from a mix of a yaml file and env vars. This requires some new and different Helm values in Phalanx (see https://mobu.lsst.io/operations/github_ci_app.html#add-phalanx-configuration)
- The GitHub CI app now takes the scopes it assigns from config values, rather than hardcoding a list of scopes.
