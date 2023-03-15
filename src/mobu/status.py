"""Post periodic status to Slack."""

from __future__ import annotations

import structlog
from safir.slack.blockkit import SlackMessage
from safir.slack.webhook import SlackWebhookClient

from .config import config
from .dependencies.manager import monkey_business_manager

__all__ = ["post_status"]


async def post_status() -> None:
    """Post a summary of mobu status to Slack.

    This is meant to be run periodically.  The primary purpose is to make it
    clear that mobu is alive, but a secondary benefit is to provide some
    summary statistics.
    """
    if not config.alert_hook or config.alert_hook == "None":
        return

    summaries = monkey_business_manager.summarize_flocks()
    flock_count = len(summaries)
    flock_plural = "flock" if flock_count == 1 else "flocks"
    text = (
        f"Currently running {flock_count} {flock_plural} against"
        f" {config.environment_url}:\n"
    )
    for summary in summaries:
        if summary.start_time:
            start_time = f'started {summary.start_time.strftime("%Y-%m-%d")}'
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

    logger = structlog.get_logger(config.logger_name)
    slack = SlackWebhookClient(config.alert_hook, "Mobu", logger)
    await slack.post(SlackMessage(message=text))
