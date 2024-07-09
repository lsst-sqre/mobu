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
      ci_config_file="github.yaml"
      ci_config_path="$config_dir/$ci_config_file"
      autostart_config_file="autostart.yaml"
      autostart_config_path="$config_dir/$autostart_config_file"

      mkdir -p "$config_dir"

      # Note: This whitespace must be actual <tab> chars!
      cat <<- 'END' > "$ci_config_path"
              users:
              - username: bot-mobu-ci-local-1
              - username: bot-mobu-ci-local-2
              accepted_github_orgs:
              - lsst-sqre
      END

      # Note: This whitespace must be actual <tab> chars!
      cat <<- 'END' > "$autostart_config_path"
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
                    repo_ref: "main"
                    max_executions: 10
                  restart: true
      END

      export MOBU_ENVIRONMENT_URL=https://data-dev.lsst.cloud
      export MOBU_GAFAELFAWR_TOKEN=$(op read "op://Employee/data-dev.lsst.cloud personal token/credential")
      export MOBU_AUTOSTART_PATH="$autostart_config_path"
      export MOBU_LOG_LEVEL=debug

      # Don't set the MOBU_GITHUB_REFRESH* vars if you don't need that integration
      export MOBU_GITHUB_REFRESH_ENABLED=true
      export MOBU_GITHUB_REFRESH_APP_WEBHOOK_SECRET=$(op read "op://RSP data-dev.lsst.cloud/mobu/github-refresh-app-webhook-secret")

      # Don't set the MOBU_GITHUB_REFRESH* vars if you don't need that integration
      export MOBU_GITHUB_CI_APP_ENABLED=true
      export MOBU_GITHUB_CI_APP_WEBHOOK_SECRET=$(op read "op://RSP data-dev.lsst.cloud/mobu/github-ci-app-webhook-secret")
      export MOBU_GITHUB_CI_APP_ID=$(op read "op://RSP data-dev.lsst.cloud/mobu/github-ci-app-id")
      export MOBU_GITHUB_CI_APP_PRIVATE_KEY=$(op read "op://RSP data-dev.lsst.cloud/mobu/github-ci-app-private-key" | base64 -d)

      # Don't set MOBU_GITHUB_CONFIG_PATH if you don't need any of the GitHub integrations.
      export MOBU_GITHUB_CONFIG_PATH="$ci_config_path"

      uvicorn mobu.main:app 2>&1

