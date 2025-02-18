"""Github webhook handlers for CI app."""

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from gidgethub import routing
from gidgethub.sansio import Event
from safir.github.webhooks import (
    GitHubCheckRunEventModel,
    GitHubCheckSuiteEventModel,
)
from safir.slack.webhook import SlackRouteErrorHandler

from ..config import Config
from ..constants import GITHUB_WEBHOOK_WAIT_SECONDS
from ..dependencies.config import config_dependency
from ..dependencies.context import RequestContext, anonymous_context_dependency
from ..dependencies.github import ci_manager_dependency
from ..services.github_ci.ci_manager import CiManager

__all__ = ["api_router"]

api_router = APIRouter(route_class=SlackRouteErrorHandler)
"""Registers incoming HTTP GitHub webhook requests"""


gidgethub_router = routing.Router()
"""Registers handlers for specific GitHub webhook payloads"""


@api_router.post(
    "/webhook",
    summary="GitHub CI webhooks",
    description="Receives webhook events from the GitHub mobu CI app.",
    status_code=202,
)
async def post_webhook(
    context: Annotated[RequestContext, Depends(anonymous_context_dependency)],
    config: Annotated[Config, Depends(config_dependency)],
    ci_manager: Annotated[CiManager, Depends(ci_manager_dependency)],
) -> None:
    """Process GitHub webhook events for the mobu CI GitHubApp.

    Rejects webhooks from organizations that are not explicitly allowed via the
    mobu config. This should be exposed via a Gafaelfawr anonymous ingress.
    """
    if config.github_ci_app is None:
        raise RuntimeError("GitHub CI app configuration is missing")
    webhook_secret = config.github_ci_app.webhook_secret
    body = await context.request.body()
    event = Event.from_http(
        context.request.headers, body, secret=webhook_secret
    )

    owner = event.data.get("organization", {}).get("login")
    if owner not in config.github_ci_app.accepted_github_orgs:
        context.logger.debug(
            "Ignoring GitHub event for unaccepted org",
            owner=owner,
            accepted_orgs=config.github_ci_app.accepted_github_orgs,
        )
        raise HTTPException(
            status_code=403,
            detail=(
                "Mobu is not configured to accept webhooks from this GitHub"
                " org."
            ),
        )

    # Bind the X-GitHub-Delivery header to the logger context; this
    # identifies the webhook request in GitHub's API and UI for
    # diagnostics
    context.rebind_logger(github_app="ci", github_delivery=event.delivery_id)
    context.logger.debug("Received GitHub webhook", payload=event.data)
    # Give GitHub some time to reach internal consistency.
    await asyncio.sleep(GITHUB_WEBHOOK_WAIT_SECONDS)
    await gidgethub_router.dispatch(
        event=event, context=context, ci_manager=ci_manager
    )


@gidgethub_router.register("check_suite", action="requested")
async def handle_check_suite_requested(
    event: Event, context: RequestContext, ci_manager: CiManager
) -> None:
    """Start a run for any check suite request with an associated PR."""
    context.rebind_logger(
        github_webhook_event_type="check_suite",
        github_webhook_action="requested",
    )
    em = GitHubCheckSuiteEventModel.model_validate(event.data)
    if not bool(em.check_suite.pull_requests):
        context.logger.debug("Ignoring; no associated pull requests")
        return

    await ci_manager.enqueue(
        installation_id=em.installation.id,
        repo_name=em.repository.name,
        repo_owner=em.repository.owner.login,
        ref=em.check_suite.head_sha,
    )

    context.logger.info("github ci webhook handled")


@gidgethub_router.register("check_suite", action="rerequested")
async def handle_check_suite_rerequested(
    event: Event, context: RequestContext, ci_manager: CiManager
) -> None:
    """Start a run for any check suite re-request with an associated PR."""
    context.rebind_logger(
        github_webhook_event_type="check_suite",
        github_webhook_action="rerequested",
    )
    em = GitHubCheckSuiteEventModel.model_validate(event.data)
    if not bool(em.check_suite.pull_requests):
        context.logger.debug("Ignoring; no associated pull requests")
        return

    await ci_manager.enqueue(
        installation_id=em.installation.id,
        repo_name=em.repository.name,
        repo_owner=em.repository.owner.login,
        ref=em.check_suite.head_sha,
    )

    context.logger.info("github ci webhook handled")


@gidgethub_router.register("check_run", action="rerequested")
async def handle_check_run_rerequested(
    event: Event, context: RequestContext, ci_manager: CiManager
) -> None:
    """Start a run for any check run re-request with an associated PR."""
    context.rebind_logger(
        github_webhook_event_type="check_run",
        github_webhook_action="rerequested",
    )
    em = GitHubCheckRunEventModel.model_validate(event.data)
    if not bool(em.check_run.pull_requests):
        context.logger.debug("Ignoring; no associated pull requests")
        return

    await ci_manager.enqueue(
        installation_id=em.installation.id,
        repo_name=em.repository.name,
        repo_owner=em.repository.owner.login,
        ref=em.check_run.head_sha,
    )

    context.logger.info("github ci webhook handled")
