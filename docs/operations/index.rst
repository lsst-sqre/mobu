##########
Operations
##########

GitHub integration
==================

Each integration has as GitHub application created in the `lsst-sqre org <https://github.com/organizations/lsst-sqre/settings/apps>`__ for every environment in which it is enabled.

All of the applications:

* `mobu refresh (data-dev.lsst.cloud) <https://github.com/organizations/lsst-sqre/settings/apps/mobu-refresh-data-dev-lsst-cloud>`__
* `mobu CI (data-dev.lsst.cloud) <https://github.com/organizations/lsst-sqre/settings/apps/mobu-ci-data-dev-lsst-cloud>`__

GitHub application configuration
================================

To enable the GitHub integrations for another mobu env, you have to create a new GitHub application and sync Phalanx secrets.

Refresh app
-----------

Create a new GitHub app
~~~~~~~~~~~~~~~~~~~~~~~


#. Click the ``New GitHub App`` button in the `lsst-sqre org Developer Settings apps page <https://github.com/organizations/lsst-sqre/settings/apps>`__.

#. Name it ``mobu refresh (<env URL or id if the URL is too long>)``.

#. Make sure the ``Active`` checkbox is checked in the ``Webhook`` section.

#. Enter ``https://<env URL>/mobu/github/refresh/webhook`` in the ``Webhook URL`` input.
#. Generate a strong password to use as the webhook secret.
#. Store this in the ``SQuaRE`` vault in the ``LSST IT`` 1Password account in an item named ``mobu GitHub refresh app webhook secret (<env URL>)``.
#. Get this into the Phalanx secret store for that env under the key: ``github-refresh-app-webhook-secret`` (`this process <https://phalanx.lsst.io/admin/add-new-secret.html>`__ is different for different envs).
#. Enter this secret in the ``Webhook secret (optional)`` box in the GitHub App config.
#. Select ``Read-only`` in the dropdown of the ``Contents`` access category in the ``Repository Permissions`` section.
#. Check the ``Push`` checkbox in the ``Subscribe to events`` section.
#. Select the ``Any account`` radio button in the ``Where can this GitHub App be installed?`` section.
#. Click the ``Create GitHub App`` button.
#. Do the `Phalanx configuration <#phalanx-configuration>`__.

Install the app for a repo
~~~~~~~~~~~~~~~~~~~~~~~~~~

#. Go to new app’s homepage (something like https://github.com/apps/mobu-refresh-usdfdev).
#. Click the ``Install`` button.
#. Select the ``Only select repositories`` radio button.
#. Select the repo in the dropdown.
#. Click ``Install``.

CI app
------

Create a new GitHub app
~~~~~~~~~~~~~~~~~~~~~~~

#. Click the ``New GitHub App`` button in the `lsst-sqre org Developer Settings apps page <https://github.com/organizations/lsst-sqre/settings/apps>`__.
#. Name it ``mobu CI (<env URL or id if the URL is too long>)``.
#. Make sure the ``Active`` checkbox is checked in the ``Webhook`` section.
#. Enter ``https://<env URL>/mobu/github/ci/webhook`` in the ``Webhook URL`` input.
#. Generate a strong password to use as the webhook secret.
#. Store this in the ``SQuaRE`` vault in the ``LSST IT`` 1Password account in an item named ``mobu GitHub CI app webhook secret (<env URL>)``.
#. Get this into the Phalanx secret store for that env under the key: ``github-ci-app-webhook-secret`` (`this process <https://phalanx.lsst.io/admin/add-new-secret.html>`__ is different for different envs).
#. Enter this secret in the ``Webhook secret (optional)`` box in the GitHub App config.
#. Select ``Read and Write`` in the dropdown of the ``Checks`` access category in the ``Repository Permissions`` section.
#. Select ``Read-only`` in the dropdown of the ``Contents`` access category in the ``Repository Permissions`` section.
#. Check the ``Check suite`` and ``Check run`` checkboxes in the ``Subscribe to events`` section.
#. Select the ``Any account`` radio button in the ``Where can this GitHub App be installed?`` section.
#. Click the ``Create GitHub App`` button.
#. Find the ``App ID`` (an integer) in the ``About`` section. Get this into the Phalanx secret store for that env under the key: ``github-ci-app-id`` (`this process <https://phalanx.lsst.io/admin/add-new-secret.html>`__ is different for different envs).
#. Click the ``Generate a private key`` button in the ``Private keys`` section.
#. Store this private key in the ``SQuaRE`` vault in the ``LSST IT`` 1Password account in an item named ``mobu GitHub CI app private key (<env URL>)``.
#. Get this into the Phalanx secret store for that env under the key: ``github-ci-app-private-key`` (`this process <https://phalanx.lsst.io/admin/add-new-secret.html>`__ is different for different envs).
#. Do the `Phalanx configuration <#phalanx-configuration>`__.

Install the app for a repo
~~~~~~~~~~~~~~~~~~~~~~~~~~

#. Go to new app’s homepage (something like https://github.com/apps/mobu-refresh-usdfdev).
#. Click the ``Install`` button.
#. Select the ``Only select repositories`` radio button.
#. Select the repo in the dropdown.
#. Click ``Install``.

Phalanx configuration
=====================

The GitHub integrations each need to be explicitly enabled in Phalanx for a given environment.
If an integration is not enabled, then the webhook route for that integration will not be mounted, GitHub webhook requests will get ``404`` responses.
To enable these integrations for an environment, set these values to ``true``:

* ``config.githubRefreshAppEnabled``
* ``config.githubCiAppEnabled``

If you want to enable either GitHub integration in a given environment, you also need to add a ``config.github`` section to that env’s values in Mobu.
That needs to be a dict with at ``users`` and ``accepted_github_orgs`` entries.
It should look something like this:

.. code:: yaml

   config:
     github:
       accepted_github_orgs:
         - lsst-sqre
       users:
         - username: "bot-mobu-ci-user-1"
           uidnumber: 123
           gidnumber: 456
         - username: "bot-mobu-ci-user-2"
           uidnumber: 789
           gidnumber: 876

The organization of any repo that uses any of the GitHub integrations in an env must be added to the ``accepted_github_orgs`` list, otherwise Github webhook requests will get ``403`` responses.

The ``users`` list follows the same rules as the ``users`` list in a flock autostart config.
The usernames must all start with ``bot-mobu``.
In envs with Firestore integration, you only need to specify ``username``.
In envs without it, you need to ensure that users are manually provisioned, and then you need all three of ``username``, ``uidnumber``, and ``gidnumber``.
