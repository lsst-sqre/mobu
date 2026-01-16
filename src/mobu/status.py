"""Post periodic status to Slack."""

from __future__ import annotations

from safir.slack.blockkit import SlackMessage

from .dependencies.context import context_dependency
from .factory import Factory

__all__ = ["post_status"]


async def post_status() -> None:
    """Post a summary of mobu status to Slack.

    This is meant to be run periodically.  The primary purpose is to make it
    clear that mobu is alive, but a secondary benefit is to provide some
    summary statistics.
    """
    process_context = context_dependency.process_context
    factory = Factory(process_context)
    slack = factory.create_slack_webhook_client()
    if not slack:
        return

    # Get the flock summaries.
    summaries = process_context.manager.summarize_flocks()
    flock_count = len(summaries)

    # Skip the status report if there are no flocks.
    if not flock_count:
        return

    # Construct the status report.
    flock_plural = "flock" if flock_count == 1 else "flocks"
    text = f"Currently running {flock_count} {flock_plural}"
    environment = await process_context.discovery_client.environment_name()
    if environment:
        text += f" against {environment}"
    text += ":\n"
    for summary in summaries:
        if summary.start_time:
            start_time = f"started {summary.start_time.strftime('%Y-%m-%d')}"
        else:
            start_time = "(not started)"
        monkey_plural = "monkey" if summary.monkey_count == 1 else "monkeys"
        failure_plural = (
            "failure" if summary.failure_count == 1 else "failures"
        )
        total = summary.success_count + summary.failure_count
        if total == 0:
            success = 100.0
        else:
            success = summary.success_count / total * 100
            if success < 100 and success > 99.995:
                success = 99.99
        line = (
            f"• *{summary.name}*: {summary.monkey_count} {monkey_plural}"
            f" {start_time} with {summary.failure_count} {failure_plural}"
            f" ({success:.2f}% success)\n"
        )
        text += line

    # Post the result to Slack.
    await slack.post(SlackMessage(message=text))
