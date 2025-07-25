###########################
Testing GitHub integrations
###########################

The GitHub integrations can be tested locally by pointing your local mobu at the ``idfdev`` env, and using a services like https://smee.io to proxy GitHub webhooks to your local mobu.

Test repo
=========
`This repo <https://github.com/lsst-sqre/dfuchs-test-mobu>`__ has a bunch of different notebooks in a bunch of different directories, some of which intentionally throw exceptions.
It contains `a script <https://github.com/lsst-sqre/dfuchs-test-mobu/blob/main/update.sh>`__ to update certain notebooks, conditionally updating the poison ones.
The `data-dev Mobu CI app <https://github.com/apps/mobu-ci-data-dev-lsst-cloud>`__ in the `lsst-sqre GitHub org <https://github.com/organizations/lsst-sqre/settings/installations/51531298>`__, is currently installed and configured to work with this repo.

smee.io
=======
You can use https://smee.io to proxy GitHub webhook requests from the data-dev Mobu CI GitHub app to your local mobu.

#. Install the tool from [smee.io](https://smee.io/).
#. Start it up and point it at your one of local mobu's GitHub webhook endpoints (the CI endpoint in this example):

   .. code-block::

      ❯ smee -p 8000 -P /mobu/github/ci/webhook
      Forwarding https://smee.io/kTysHB50d4pgUmRN to http://127.0.0.1:8000/mobu/github/ci/webhook

#. Configure the [data-dev GitHub Mobu CI app](https://github.com/organizations/lsst-sqre/settings/apps/mobu-ci-data-dev-lsst-cloud) to send webooks to the smee URL.
#. Run your local mobu against the ``idfdev`` env, as described :doc:`here <idfdev>`.
#. Point your local mobu at a local or remote git `Safir <https://github.com/lsst-sqre/safir>`__ .

   .. code-block:: diff

      index ce732db..ce2d693 100644
      --- a/requirements/main.in
      +++ b/requirements/main.in
      @@ -22,6 +22,6 @@ pydantic-settings
       pyvo
       pyyaml
      -safir>=5.0.0
      +# safir>=5.0.0

      # For testing against a local safir
      +-e /home/danfuchs/src/safir/safir

      # For testing against a remote git safir
      +safir @ git+https://github.com/lsst-sqre/safir@<branch>#subdirectory=safir
       shortuuid
       structlog

#. Patch your local or remote git Safir to handle the malformed requests that smee.io sends.
   The requests sent by the smee proxy have ``:port`` suffixes in the ``X-Forwarded-For`` values.
   Safir doesn't handle this (and I don't think it's Safir's fault; I _think_ the port should be in ``X-Forwarded-Port``), so you have to change Safir:

   .. code-block:: diff

      index 2a3f40c..7211241 100644
      --- a/src/safir/middleware/x_forwarded.py
      +++ b/src/safir/middleware/x_forwarded.py
      @@ -116,5 +116,5 @@ class XForwardedMiddleware:
               return [
                   ip_address(addr)
      -            for addr in (a.strip() for a in forwarded_for_str[0].split(","))
      +            for addr, _ in (a.strip().split(':') for a in forwarded_for_str[0].split(","))
                   if addr
               ]
