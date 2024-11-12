##########################
Testing against ``idfdev``
##########################

You can run mobu locally while having all of the actual business run against services in ``idefdev`` (or any other environment).


#. Install the `1Password CLI <https://developer.1password.com/docs/cli/>`__.
#. Generate a personal `idfdev gafaelfawr token <https://data-dev.lsst.cloud/auth/tokens/>`__ generated with an ``admin:token`` scope.
#. Put this token in a ``data-dev.lsst.cloud personal token`` entry in your personal 1Password vault.
#. Run mobu locally with something like this shell script:

   .. code-block:: shell

      #!/usr/bin/env bash

      set -euo pipefail

      config_dir="/tmp/mobu_test"
      config_file="mobu_config.yaml"
      config_path="$config_dir/$config_file"

      mkdir -p "$config_dir"

      # Note: This whitespace must be actual <tab> chars!
      cat <<-'END' >"$config_path"
          logLevel: debug
          githubRefreshApp:
            acceptedGithubOrgs:
            - lsst-sqre
          githubCiApp:
            users:
              - username: bot-mobu-ci-local-1
              - username: bot-mobu-ci-local-2
            scopes:
              - "exec:notebook"
              - "exec:portal"
              - "read:image"
              - "read:tap"
            acceptedGithubOrgs:
              - lsst-sqre
          autostart:
            - name: "my-test"
              count: 1
              users:
                - username: "bot-mobu-my-test-local"
              scopes:
                - "exec:notebook"
              business:
                type: "NotebookRunner"
                options:
                  repo_url: "https://github.com/lsst-sqre/dfuchs-test-mobu.git"
                  repo_ref: "dfuchs-test-pr"
                  max_executions: 10
                restart: true
            - name: "my-other-test"
              count: 1
              users:
                - username: "bot-mobu-my-test-local2"
              scopes:
                - "exec:notebook"
              business:
                type: "NotebookRunner"
                options:
                  repo_url: "https://github.com/lsst-sqre/dfuchs-test-mobu.git"
                  repo_ref: "main"
                  max_executions: 10
                restart: true
            - name: "dfuchs-test-tap"
              count: 1
              users:
                - username: "bot-mobu-dfuchs-test-tap"
              scopes: ["read:tap"]
              business:
                type: "TAPQuerySetRunner"
                options:
                  query_set: "dp0.2"
                restart: true
            - name: "tap"
              count: 1
              users:
                - username: "bot-mobu-dfuchs-test-tap-query"
              scopes: ["read:tap"]
              business:
                type: "TAPQueryRunner"
                options:
                  queries:
                    - "SELECT TOP 10 * FROM  TAP_SCHEMA.tables"
                restart: true
      END

      export MOBU_CONFIG_PATH="$config_path"
      export MOBU_ENVIRONMENT_URL=https://data-dev.lsst.cloud
      export MOBU_GAFAELFAWR_TOKEN=$(op read "op://Employee/data-dev.lsst.cloud personal token/credential")
      export MOBU_GITHUB_REFRESH_APP_WEBHOOK_SECRET=$(op read "op://RSP data-dev.lsst.cloud/mobu/github-refresh-app-webhook-secret")
      export MOBU_GITHUB_CI_APP_WEBHOOK_SECRET=$(op read "op://RSP data-dev.lsst.cloud/mobu/github-ci-app-webhook-secret")
      export MOBU_GITHUB_CI_APP_ID=$(op read "op://RSP data-dev.lsst.cloud/mobu/github-ci-app-id")
      export MOBU_GITHUB_CI_APP_PRIVATE_KEY=$(op read "op://RSP data-dev.lsst.cloud/mobu/github-ci-app-private-key" | base64 -d)
      export UVICORN_PORT=8001

      uvicorn mobu.main:create_app 2>&1
