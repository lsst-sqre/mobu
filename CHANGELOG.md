# Change log

mobu is versioned with [semver](https://semver.org/). Dependencies are updated to the latest available version during each release. Those changes are not noted here explicitly.

Find changes for the upcoming release in the project's [changelog.d](https://github.com/lsst-sqre/mobu/tree/main/changelog.d/).

<!-- scriv-insert-here -->

<a id='changelog-16.0.0'></a>
## 16.0.0 (2025-07-10)

### Backwards-incompatible changes

- The GitHub Mobu CI app now listens to `pull_request` events instead of `check_suite` and `check_run` events. When this version of mobu is deployed to an environment, the app permissions and subscribed events  in the `Permission & Events` tab of the Developer Settings for the app need to be modified.

  The permissions in the `Repository permissions` accordian section need to be changed:
  - In the `Pull requests` row, change the `Access` drop-down to `Read-only`

  The events in `Subscribe to events` section of the `Permissions & Events` tab have to be changed:
  - Uncheck the `Check run` box
  - Uncheck the `Check suite` box
  - Check the `Pull request` box

  This fixes a bug where a Mobu CI job would never run when a PR was opened.

<a id='changelog-15.4.0'></a>
## 15.4.0 (2025-07-02)

### New features

- Support setting supplemental groups for users, allowing mobu to test services that use group membership for access control.

### Other changes

- Use [uv](https://github.com/astral-sh/uv) to maintain frozen dependencies and set up a development environment.

<a id='changelog-15.3.1'></a>
## 15.3.1 (2025-06-30)

### Bug fixes

- Notebook cache now only re-clones once after invalidation. Previously, it could get into a re-clone loop.
- GitHub refresh doesn't break now for flocks with multiple monkeys running repos with multiple notebooks.

<a id='changelog-15.3.0'></a>
## 15.3.0 (2025-06-26)

### New features

- Make notebook filtering simpler and more flexible.

  * Deprecate `exclude_dirs`
  * Add `collection_rules` to every notebookrunner business, not just `NotebookRunnerList`

  `collection_rules` looks like this:

  ```yaml
     collection_rules:
       - type: "exclude_union_of"
         patterns:
           - "not-these/**"
           - "not/these/either/**"
       - type: "intersect_union_of"
         patterns:
           - "this.ipynb"
           - "these/**"
           - "also/these**"
       - type: "intersect_union_of"
         patterns:
           - "**/these-*"
  ```

  Each entry is a pattern using the [Python pathlib glob pattern language](https://docs.python.org/3/library/pathlib.html#pathlib-pattern-language)

* Start with all notebooks in the repo.
* For each collection rule, remove notebooks:
  * Intersect rules will remove notebooks that are not in the
    intersection of:
      * The current set
      * The union of the matched patterns.
  * Exclude rules will remove notebooks from the current set that are
    in the union of the matched patterns.
* Remove any remaining notebooks that require unavailable services.

<a id='changelog-15.2.0'></a>
## 15.2.0 (2025-05-20)

### New features

- Add a new `notebook_idle_time` config parameter to all `NotebookRunner`-based to configure how long to wait in between each notebook execution.

<a id='changelog-15.1.0'></a>
## 15.1.0 (2025-03-20)

### New features

- Multiple replicas of mobu can be run in an environment. The number of monkeys specified in a flock's `count` will be spread evenly across all replicas. Note that this comes with certain restrictions, see [the docs](https://mobu.lsst.io/user-guide/multiple-replicas.html) for details.

### Bug fixes

- Do not send a summary message to Slack if there are no flocks running.

- One period of `execution_idle_time` elapses after trying to execute a notebook with no code cells, instead of not waiting at all.

<a id='changelog-15.0.0'></a>
## 15.0.0 (2025-03-17)

### Backwards-incompatible changes

- The `NotebookRunner` buisiness has been split into two different businesses: `NotebookRunnerCounting` and `NotebookRunnerList`. The difference is that `NotebookRunnerCounting` takes the `max_executions` option that refreshes the lab after that number of notebook executions, and `NotebookRunnerList` takes the `notebooks_to_run` option, which runs all of the notebooks in that list before refreshing. Currently, `NotebookRunnerList` is only used by the GitHub CI functionality. Any references to `NotebookRunner` in any flock config need to be changed to to one of these new businesses, almost certainly `NotebookRunnerCounting`.

### New features

- Add support for running against Nublado configured with user subdomains.
- Add a `gafaelfawr_timeout` config option. With very large numbers of users, like for scale testing, the default httpx timeouts from the [safir http client](https://safir.lsst.io/user-guide/http-client.html) may not be long enough.
- Add new `NotebookRunnerInfinite` business that does not interact further with JupyterHub after the notebook has been spawned, avoiding the pings mobu normally uses to refresh authentication credentials. This is a closer match to the typical access pattern for a regular user.

### Bug fixes

- Batch Gafaelfawr token creations in groups of 10 instead of attempting to perform them all in parallel. Gafaelfawr has to serialize them on database transactions anyway, so running all token creations at once with a large flock causes problems with HTTP request timeouts.

<a id='changelog-14.2.1'></a>
## 14.2.1 (2025-02-26)

### Bug fixes

- Avoid an unbound variable exception during a Nublado client error handling path.

<a id='changelog-14.2.0'></a>
## 14.2.0 (2025-02-26)

### New features

- Add SIAv2 QuerySet runner, which uses `pyvo.search` to query the DP0.2 SIAv2 service.

### Bug fixes

- CI jobs will now run all notebooks included in the PR, not just the ones changed in the latest commit. This fixes the case where the latest commit only fixes one of multiple bad notebooks in a PR, but passes the Mobu CI check.

<a id='changelog-14.1.0'></a>
## 14.1.0 (2025-02-20)

### New features

- All time durations in business configurations can now be given as human-readable durations with suffixes such as `h`, `m`, and `s`. For example, `5m30s` indicates a duration of five minutes and thirty seconds, or 330 seconds.
- Add `log_monkeys_to_file` config option to choose whether to write monkey logs to files or console.
- Add `start_batch_size` and `start_batch_wait` flock config parameters to allow starting monkeys in a slower and more controlled way.

### Bug fixes

- When starting a flock, create user tokens simultaneously (up to the limit of the httpx connection pool size of 100) rather than serially.
- Fix jitter calculations in Nublado businesses.
- Notebook repos are only cloned once per process (and once per refresh request), instead of once per monkey. This should speed up how fast NotebookRunner flocks start, especially in load testing usecases.

### Other changes

- Modify TAPBusiness to use pyvo's `run_async` instead of using `submit_job` and polling.

<a id='changelog-14.0.0'></a>
## 14.0.0 (2025-01-31)

### Backwards-incompatible changes

- Instrument tracing and exception handling with Sentry. All timings are now calculated with Sentry tracing functionality, and all Slack notifications for errors come from Sentry instead of the Safir `SlackException` machinery.

### New features

- Send an app metrics event for `EmptyLoop` business iterations.
- Remove the limit from the autostart aiojobs `Scheduler`. Attempts to start a job past the limit resulted in jobs silently never starting. There are no cases where we would want to limit the autostart concurrency, so a limit is not needed.

<a id='changelog-13.2.0'></a>
## 13.2.0 (2024-12-17)

### New features

- Publish [application metrics](https://safir.lsst.io/user-guide/metrics/index.html).

<a id='changelog-13.0.1'></a>
## 13.0.1 (2024-11-19)

### Bug fixes

- Fix handling of Jupyter XSRF cookies.

<a id='changelog-13.0.0'></a>
## 13.0.0 (2024-11-12)

### Backwards-incompatible changes

- All app config, including autostart config (and excluding secrets, which still come from environment variables) now comes from a single YAML file, provisioned by a single `ConfigMap` in Phalanx.

<a id='changelog-12.0.2'></a>
## 12.0.2 (2024-10-31)

### Bug fixes

- Improve exception reports from the Nublado client.

<a id='changelog-12.0.1'></a>
## 12.0.1 (2024-10-29)

### Bug fixes

- Fix exceptions in the Nublado notebook runner caused by not having the cell ID.

<a id='changelog-12.0.0'></a>
## 12.0.0 (2024-10-28)

### Other changes

- Replace the internal Nublado client with the new client released to PyPI.

<a id='changelog-11.0.0'></a>
## 11.0.0 (2024-08-06)

### Backwards-incompatible changes

- Remove `exclude_dirs` option from `NotebookRunner` options, which means it can no longer be set in the autostart config. `exclude_dirs` must be set in an in-repo `mobu.yaml` config file.

### New features

- `NotebookRunner` business will skip notebooks in environments that do not have the services required for them to run. Required services ban be declared by adding [metadata](https://ipython.readthedocs.io/en/3.x/notebook/nbformat.html#metadata) to a notebook.
- Allow specification of the log level for individual flocks.

### Bug fixes

- Inspect individual redirects for JupyterHub logins as well as JupyterLab to get updated XSRF cookies.

<a id='changelog-10.1.0'></a>
## 10.1.0 (2024-07-12)

### Other changes

- Update to the latest Safir release with GitHub model changes.

<a id='changelog-10.0.0'></a>
## 10.0.0 (2024-07-11)

### Backwards-incompatible changes

- GitHub CI and refresh app config are now each a separate, all-or-nothing set of config that comes from a mix of a yaml file and env vars. This requires some new and different Helm values in Phalanx (see https://mobu.lsst.io/operations/github-ci-app.html#add-phalanx-configuration)
- The GitHub CI app now takes the scopes it assigns from config values, rather than hardcoding a list of scopes.

<a id='changelog-9.0.0'></a>
## 9.0.0 (2024-07-09)

### Backwards-incompatible changes

- The existing refresh functionality is now a GitHub app integration (from a simple webhook integration). This requires new Phalanx secrets to be sync'd, and a new GitHub app to be added to repos that want the functionality. Special care has been taken to not leave these checks in a forever-in-progress state, even in the case of (graceful) mobu shutdown/restart

### New features

- A GitHub app integration to generate GitHub actions checks for commits pushed to notebook repo branches that are part of active PRs. These checks trigger and report on a solitary Mobu run of the changed notebooks in the commit.

<a id='changelog-8.1.0'></a>
## 8.1.0 (2024-05-30)

### New features

- `NotebookRunner` flocks can now pick up changes to their notebooks without having to restart the whole mobu process. This refresh can happen via:
  - GitHub `push` webhook post to `/mobu/github/webhook` with changes to a repo and branch that matches the flock config
  - `monkeyflocker refresh <flock>`
  - `POST` to `/mobu/flocks/{flock}/refresh`

<a id='changelog-8.0.0'></a>
## 8.0.0 (2024-05-21)

### Backwards-incompatible changes

- NotebookRunner business now runs all notebooks in a repo, at tht root and in all subdirs recursively, by default.
- Add `exclude_dirs` option to NotebookRunner business to list directories in which notebooks will not be run.

<a id='changelog-7.1.1'></a>
## 7.1.1 (2024-03-28)

### Bug fixes

- Correctly extract cookies from the middle of the redirect chain caused by initial authentication to a Nublado lab. This fixes failures seen with labs containing JupyterHub 4.1.3.

<a id='changelog-7.1.0'></a>
## 7.1.0 (2024-03-21)

### New features

- Add `GitLFSBusiness` for testing Git LFS by storing and retrieving a Git LFS-managed artifact.

### Bug fixes

- Properly handle the XSRF tokens for JupyterHub and the Jupyter lab by storing separate tokens for the hub and lab after initial login and sending the appropriate XSRF token in the `X-XSRFToken` header to the relevant APIs. This fixes a redirect loop at the Jupyter lab when running 4.1.0 or later.

### Other changes

- mobu now uses [uv](https://github.com/astral-sh/uv) to maintain frozen dependencies and set up a development environment.

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
- mobu now uses the [Ruff](https://docs.astral.sh/ruff/) linter instead of flake8, isort, and pydocstyle.

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
