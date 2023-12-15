# Change log

mobu is versioned with [semver](https://semver.org/). Dependencies are updated to the latest available version during each release. Those changes are not noted here explicitly.

Find changes for the upcoming release in the project's [changelog.d](https://github.com/lsst-sqre/mobu/tree/main/changelog.d/).

<!-- scriv-insert-here -->

<a id='changelog-7.0.0'></a>
## 7.0.0 (2023-12-15)

### Backwards-incompatible changes

- Drop support for cachemachine and Nublado v2. The `cachemachine_image_policy` and `use_cachemachine` configuration options are no longer supported and should be deleted.
- Rename the existing `TAPQueryRunner` business to `TAPQuerySetRunner` to more accurately capture what it does. Add a new `TAPQueryRunner` business that runs queries chosen randomly from a list. Based on work by @stvoutsin.
- Rename `JupyterPythonLoop` to `NubladoPythonLoop` to make it explicit that it requires Nublado and will not work with an arbitrary JupyterHub.

### New features

- Convert all configuration options that took intervals in seconds to `timedelta`. Bare numbers will still be interpreted as a number of seconds, but any format Pydantic recognizes as a `timedelta` may now be used.

### Other changes

- All environment variables used to configure mobu now start with `MOBU_`, and several have changed their names. The new settings are `MOBU_ALERT_HOOK`, `MOBU_AUTOSTART_PATH`, `MOBU_ENVIRONMENT_URL`, `MOBU_GAFAELFAWR_TOKEN`, `MOBU_NAME`, `MOBU_PATH_PREFIX`, `MOBU_LOGGING_PROFILE`, and `MOBU_LOG_LEVEL`. This is handled by the Phalanx application, so no configuration changes should be required.

<a id='changelog-6.1.1'></a>
## 6.1.1 (2023-07-06)

### Bug fixes

- Rather than dumping the full monkey data when summarizing flocks, which can cause long enough delays that in-progress calls fail due to the huge amount of timing data, extract only the success and failure count from the running business. This should be considerably faster and avoid timeout problems.
- Improve error reporting by catching exceptions thrown while sending code to the lab WebSocket for execution.

<a id='changelog-6.1.0'></a>
## 6.1.0 (2023-05-31)

### New features

- The timeout when talking to JupyterHub and Jupyter labs can now be configured in the business options (as ``jupyter_timeout``). The default is now 60s instead of 30s.

### Bug fixes

- When reporting httpx failures to Slack, put the response body into an attachment instead of a block so that it will be collapsed if long.
- Fix reporting of WebSocket open timeouts to Slack.

<a id='changelog-6.0.0'></a>
## 6.0.0 (2023-05-22)

### Backwards-incompatible changes

- Configuration of whether to use cachemachine and, if so, what image policy to use is now done at the business level instead of globally. This allows the same mobu instance to test both Nublado v2 and Nublado v3.

### New features

- The maximum allowable size for a WebSocket message from the Jupyter lab is now configurable per business and defaults to 10MB instead of 4MB.

### Bug fixes

- Revert change in 5.0.0 to number all cells, and go back to counting only code cells for numbering purposes. This matches the way cell numbers are displayed in the Jupyter lab UI.
- When reporting errors to Slack, mobu 5.0.0 mistakenly started stripping ANSI escape sequences from the code being executed, which should be safe since it comes from local notebooks or configuration, instead of the error output, which is where Jupyter labs like to add formatting. Strip ANSI escape sequences from the error output instead of the code.

<a id='changelog-5.1.0'></a>
## 5.1.0 (2023-05-15)

### New features

- mobu now uses httpx instead of aiohttp for all HTTP requests (including websockets for WebSocket connections and httpx-sse for EventStream connections) and makes use of the Safir framework for parsing and reporting HTTP client exceptions. Alerts for failing web requests will be somewhat different and hopefully clearer.
- mobu now sends keep-alive pings on the WebSocket connection to the lab, hopefully allowing successful execution of cells that take more than five minutes to run.
- Nublado-based businesses can now set `debug` to true in the image specification to request that debugging be enabled in the spawned Jupyter lab.
- mobu now catches timeouts attempting to open a WebSocket to the lab and reports them to Slack with more details.
- Slack alerts from monkeys now include the flock and monkey name as a field in the alert.
- Unexpected business exceptions now include an "Exception type" heading and use "Failed at" instead of "Date" to match the display of expected exceptions.
- The prefix for mobu routes (`/mobu` by default) can now be configured with `SAFIR_PATH_PREFIX`.
- Uncaught exceptions from mobu's route handlers are now also reported to Slack.

### Bug fixes

- The code to determine the Docker reference and description of the running Nublado image is now more robust against unexpected output.
- Node and cell information in Slack error reports for Nublado errors are now formatted as full blocks rather than fields, since they are often too wide to fit nicely in the limited width of a Slack Block Kit field.

### Other changes

- The default `error_idle_time` for Nublado-based business is back to 60 seconds instead of 10 minutes. The problem the longer timeout was working around should be fixed in the new Nublado lab controller.
- Nublado-based notebooks now request the `JUPYTER_IMAGE_SPEC` environment variable instead of `JUPYTER_IMAGE` to get the running image for error reporting purposes. This is now the preferred environment variable and `JUPYTER_IMAGE` is deprecated.
- mobu now uses the [Ruff](https://beta.ruff.rs/docs/) linter instead of flake8, isort, and pydocstyle.

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
