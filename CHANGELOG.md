# Change log

Versioning follows [semver](https://semver.org/).

Dependencies are updated to the latest available version during each release. Those changes are not noted here explicitly.

## 5.0.1 (unreleased)

### Bug fixes

- The code to determine the Docker reference and description of the running Nublado image is now more robust against unexpected output.

## 5.0.0 (2023-03-22)

### Backwards-incompatible changes

- Settings are now handled with Pydantic and undergo much stricter validation. In particular, the Slack web hook URL must now be a valid URL if provided.
- In order to enable stricter and more useful Pydantic validation of flock specifications, the syntax for creating a flock has changed. `business` is now a dictionary, the `restart` option has been moved under it, the type of business is specified with `type`, and the business configuration options have moved under that key as `options`. Options that are not applicable to a given business type are now rejected.
- The `jupyter.url_prefix` option is now just `url_prefix`, and `juyter.image` is now just `image`. The names of the setting under `image` have changed.
- The `TAPQueryRunner` options `tap_sync` and `tap_query_set` are now just `sync` and `query_set`.
- `lab_settle_time` is no longer supported as a configuration option for the businesses that spawn a Nublado lab. It defaulted to 0 and we never set it.
- `JupyterJitterLoginLoop` has been retired. Instead, set the `jitter` option on `JupyterPythonLoop`.
- `JupyterLoginLoop` has been merged with `JupyterPythonLoop`. The only difference in the former is that no lab session was created and no code was run, which seems pointless and not worth the distinction. `JupyterPythonLoop` runs a simple addition by default, which should be an improvement over `JupyterLoginLoop` in every likely situation.

### New features

- When the production logging profile is used, the messages from monkeys are no longer reported to the main mobu log, only to the individual monkey logs. This should produce considerably less noise in external log aggregators.
- The notebook being run is now included in all Slack error reports, not just for code execution failures.
- The API documentation now shows only the relevant options for the type of business when showing how to create a flock.
- Add support for running a business once and returning its results, via a POST to the new `/run` endpoint.
- Add support for the new Nublado lab controller (see [SQR-066](https://sqr-066.lsst.io/).
- The time a business pauses after a failure before it is restarted is now configurable with the `error_idle_time` option and defaults to 10 minutes (instead of 1 minute) for Nublado businesses, since this is how long JupyterHub will wait for a lab to spawn before giving up.

### Bug fixes

- The `dp0.2` `TAPQueryRunner` query set is now lighter-weight and will consume less memory and CPU to execute, hopefully reducing timeout errors.
- Cell numbering in error reports is now across all cells, not just code cells.
- `TAPQueryRunner` no longer creates a TAP client in its `__init__` method, since creating a TAP client makes HTTP requests to the TAP server that can fail and failure would potentially crash mobu. Instead, it creates the TAP client in `startup` and handles exceptions properly so that they're reported to Slack.
- Business failures during `startup` are now counted as a failed execution so that a business that fails repeatedly in `startup` doesn't report 100% success in the flock summary.
- The code run by `JupyterPythonLoop` and `NotebookRunner` to get the Kubernetes node on which the lab is running now uses `lsst.rsp.get_node` instead of the deprecated `rubin_jupyer_utils.lab.notebook.utils.get_node`.

### Other changes

- Slightly improve logging when monkeys are shut down due to errors.
- mobu's internals have been extensively refactored following the design in [SQR-072](https://sqr-072.lsst.io/) to hopefully make future maintenance easier.
