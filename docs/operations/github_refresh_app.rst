###########################################
Adding a new GitHub Refresh app integration
###########################################

Adding the GitHub refresh app integration to a new environment requires configuring things in GitHub and Phalanx.

Create a new GitHub app
=======================


#. Click the ``New GitHub App`` button in the `lsst-sqre org Developer Settings apps page <https://github.com/organizations/lsst-sqre/settings/apps>`__.
#. Name it :samp:`mobu refresh ({env URL or id if the URL is too long})`.
#. Make sure the :guilabel:`Active` checkbox is checked in the :guilabel:`Webhook` section.
#. Enter :samp:`https://{env URL}/mobu/github/refresh/webhook` in the :guilabel:`Webhook URL` input.
#. Generate a strong password to use as the webhook secret.
#. Store this in the ``SQuaRE`` vault in the ``LSST IT`` 1Password account in an ``Server`` item named :samp:`mobu ({env URL})` in a ``password`` field called ``github-refresh-app-webhook-secret``.
#. Get this into the Phalanx secret store for that env under the key: ``github-refresh-app-webhook-secret`` (`this process <https://phalanx.lsst.io/admin/add-new-secret.html>`__ is different for different envs).
#. Enter this secret in the :guilabel:`Webhook secret (optional)` box in the GitHub App config.
#. Select :menuselection:`Read and Write` in the dropdown of the :guilabel:`Checks` access category in the :guilabel:`Repository Permissions` section.
#. Select :menuselection:`Read-only` in the dropdown of the :guilabel:`Contents` access category in the :guilabel:`Repository Permissions` section.
#. Check the :guilabel:`Check suite` and :guilabel:`Check run` checkboxes in the :guilabel:`Subscribe to events` section.
#. Select the :guilabel:`Any account` radio button in the :guilabel:`Where can this GitHub App be installed?` section.
#. Click the :guilabel:`Create GitHub App` button.

Install the app for a repo
==========================

#. Go to new app’s homepage (something like https://github.com/apps/mobu-refresh-usdfdev).
#. Click the :guilabel:`Install` button.
#. Select the :guilabel:`Only select repositories` radio button.
#. Select the repo in the dropdown.
#. Click :guilabel:`Install`.

Add Phalanx configuration
=========================
In :samp:`applications/mobu/values-{env}.yaml`, add a ``config.githubRefreshApp`` value:

.. code:: yaml

   config:
     githubRefreshApp:
       acceptedGithubOrgs:
         - lsst-sqre

All of these items are required.

``accepted_github_orgs``
    A list of GitHub organizations from which this instance of Mobu will accept webhook requests.
    Webhook requests from any orgs not in this list will get a ``403`` response.
