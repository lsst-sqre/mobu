### Backwards-incompatible changes

- Instrument tracing and exception handling with Sentry. All timings are now calculated with Sentry tracing functionality, and all Slack notifications for errors come from Sentry instead of the Safir `SlackException` machinery.
