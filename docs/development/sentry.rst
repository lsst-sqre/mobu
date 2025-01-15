##################
Sentry Integration
##################

Mobu integrates with Sentry differently than most other apps, because the unit of work isn't a request like in a web app, it's an iteration (or part of an iteration) of a business.
As a result, some things are different about this Sentry integration.

Scopes and Transactions
=======================

`Isolation scopes <https://docs.sentry.io/platforms/python/enriching-events/scopes/>`_ and `transactions <https://docs.sentry.io/platforms/python/tracing/instrumentation/custom-instrumentation/#add-a-transaction>`_ are created manually.
All tags and contexts are set on the isolation scope, and any exceptions are manually captured in the monkey runner loop.

* There is one isolation scope for every execution of a business's ``run`` method.
* There is one transaction for every execution of a business's ``run`` method.
* For ``Nublado`` businesses, there are transactions created for startup and shutdown.
* For ``NotebookRunner`` businesses, a transaction is created for every notebook execution.

The details of the notebook execution transactions, or the startup and shutdown transactions, will not appear in the main business iteration transaction.
We have these separate inner transactions because Sentry waits until all spans are closed in a transaction before sending it, and we don't want to wait for ``max_executions`` notebook executions before tracing information for a single notebook executions is sent.

Fingerprints
============

We add tags to the fingerprint of every event sent to Sentry to force the creation of separate issues where only one issue would be created by default.
For example, we add notebook and cell ids to the fingerprint to force different issues (and thus different notifications) for errors from different notebooks and cells.

Traces Sampling
===============

The ``sentry_traces_sample_config``/``sentryTracesSampleConfig`` option can be set to:

* A float, in which case it will be passed directly to `traces_sample_rate <https://docs.sentry.io/platforms/python/configuration/options/#traces-sample-rate>`_ when initializing Sentry, and only send that percentage of transactions to Sentry
* The string "errors", in which case transactions will be sent to Sentry only if errors occurred during them
