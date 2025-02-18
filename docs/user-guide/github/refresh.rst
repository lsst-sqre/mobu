############################
Auto-refresh notebook flocks
############################

Problem
   You have a GitHub repo filled with Python notebooks.
   You’ve already configured Mobu to run a flock that executes these notebooks.
   But every time you commit changes to the notebooks in this repo, you have to restart Mobu to get it to pick up the changes!

Solution
   Enable a GitHub app for your repo, and Mobu will automatically pick up any changes.

Configuration
=============

There is a ``mobu refresh (<env url>)`` GitHub app for every environment that runs Mobu (Except environments behind a VPN).
For every environment in which you want your repo to auto refresh, you have to install the app in your repo's organization, and enable the app for your repo.

Install the app
---------------
If it's not already installed, that is.

#. Have a Mobu autorun flock configured and running.
#. Install that environment’s ``mobu refresh`` app in your repo’s GitHub organization.
   Someone with appropriate permissions can do that from the `app’s homepage <#mobu-refresh-github-app-urls>`__.
#. Add your organization to the ``accetped_github_orgs`` list in the Mobu configuration in Phalanx for the matching env.

Enable the app for your repo
----------------------------

#. Go to your repo’s organization settings page in GitHub, and go to the “GitHub Apps” page in the “Third-party Access” section in the left sidebar.
   `Here <https://github.com/organizations/lsst-sqre/settings/installations>`__ is that page for the ``lsst-sqre`` organization.
#. Click the ``Configure`` button in the ``mobu refresh (<env url>)`` row.
#. In the “Repository access” section, click the “Select repositories” dropdown and add your repository.

Mobu refresh GitHub app URLs
============================

-  `data-dev.lsst.cloud <https://github.com/apps/mobu-refresh-data-dev-lsst-cloud>`__

