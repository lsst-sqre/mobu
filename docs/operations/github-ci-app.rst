######################################
Adding a new GitHub CI app integration
######################################


Create a new GitHub app
=======================

#. Click the ``New GitHub App`` button in the `lsst-sqre org Developer Settings apps page <https://github.com/organizations/lsst-sqre/settings/apps>`__.
#. Name it :samp:`mobu CI ({env URL or id if the URL is too long})`.
#. Make sure the ``Active`` checkbox is checked in the ``Webhook`` section.
#. Enter :samp:`https://{env URL}/mobu/github/ci/webhook` in the :guilabel:`Webhook URL` input.
#. Generate a strong password to use as the webhook secret.
#. Store this in the ``SQuaRE`` vault in the ``LSST IT`` 1Password account in an ``Server`` item named :samp:`mobu ({env URL})` in a ``password`` field named ``mobu-github-ci-app-webhook-secret``.
#. Get this into the Phalanx secret store for that env under the key: ``github-ci-app-webhook-secret`` (`this process <https://phalanx.lsst.io/admin/add-new-secret.html>`__ is different for different envs).
#. Enter this secret in the :guilabel:`Webhook secret (optional)` box in the GitHub App config.
#. Select :menuselection:`Read and Write` in the dropdown of the :guilabel:`Checks` access category in the :guilabel:`Repository Permissions` section.
#. Select :menuselection:`Read-only` in the dropdown of the :guilabel:`Contents` access category in the :guilabel:`Repository Permissions` section.
#. Select :menuselection:`Read-only` in the dropdown of the :guilabel:`Pull requests` access category in the :guilabel:`Repository Permissions` section.
#. Check the :guilabel:`Pull request` checkbox in the :guilabel:`Subscribe to events` section.
#. Select the :guilabel:`Any account` radio button in the :guilabel:`Where can this GitHub App be installed?` section.
#. Click the :guilabel:`Create GitHub App` button.
#. Find the :guilabel:`App ID` (an integer) in the :guilabel:`About` section. Get this into the Phalanx secret store for that env under the key: ``github-ci-app-id`` (`this process <https://phalanx.lsst.io/admin/add-new-secret.html>`__ is different for different envs).
#. Click the :guilabel:`Generate a private key` button in the :guilabel:`Private keys` section.
#. Store this private key in the same :samp:`mobu ({env URL})` item in a ``text`` key called ``github-mobu-ci-app-private-key``.
#. Get this into the Phalanx secret store for that env under the key: ``github-ci-app-private-key`` (`this process <https://phalanx.lsst.io/admin/add-new-secret.html>`__ is different for different envs).

Install the app for a repo
==========================

#. Go to new app’s homepage (something like https://github.com/apps/mobu-refresh-usdfdev).
#. Click the :guilabel:`Install` button.
#. Select the :guilabel:`Only select repositories` radio button.
#. Select the repo in the dropdown.
#. Click :guilabel:`Install`.

Add Phalanx configuration
=========================
In :samp:`applications/mobu/values-{env}.yaml`, add a ``config.githubCiApp`` value:

.. code:: yaml

   config:
     githubCiApp:
       acceptedGithubOrgs:
         - lsst-sqre
       users:
         - username: "bot-mobu-ci-user-1"
           uidnumber: 123
           gidnumber: 456
         - username: "bot-mobu-ci-user-2"
           uidnumber: 789
           gidnumber: 876
       scopes:
         - "exec:notebook"
         - "exec:portal"
         - "read:image"
         - "read:tap"

All items are required.

``acceptedGithubOrgs``
    A list of GitHub organizations from which this instance of Mobu will accept webhook requests.
    Webhook requests from any orgs not in this list will get a ``403`` response.

``users``
    Follows the same rules as the ``users`` list in a flock autostart config.
    The usernames must all start with ``bot-mobu``.
    In envs with Firestore integration, you only need to specify ``username``.
    In envs without it, you need to ensure that users are manually provisioned, and then you need all three of ``username``, ``uidnumber``, and ``gidnumber``.

``scopes``
    A list of `Gafaelfawr scopes <https://dmtn-235.lsst.io/#current-scopes>`__ to grant to the users running in the monkeys started from GitHub CI checks.
