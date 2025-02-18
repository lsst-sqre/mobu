"""Github webhook handlers for CI app."""

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from gidgethub import routing
from gidgethub.sansio import Event
from safir.github.webhooks import GitHubPushEventModel
from safir.slack.webhook import SlackRouteErrorHandler

from ..config import Config
from ..constants import GITHUB_WEBHOOK_WAIT_SECONDS
from ..dependencies.config import config_dependency
from ..dependencies.context import RequestContext, anonymous_context_dependency

__all__ = ["api_router"]

api_router = APIRouter(route_class=SlackRouteErrorHandler)
"""Registers incoming HTTP GitHub webhook requests"""


gidgethub_router = routing.Router()
"""Registers handlers for specific GitHub webhook payloads"""


@api_router.post(
    "/webhook",
    summary="GitHub refresh webhooks",
    description="Receives webhook events from the GitHub mobu refresh app.",
    status_code=202,
)
async def post_webhook(
    context: Annotated[RequestContext, Depends(anonymous_context_dependency)],
    config: Annotated[Config, Depends(config_dependency)],
) -> None:
    """Process GitHub webhook events for the mobu refresh GitHub app.

    Rejects webhooks from organizations that are not explicitly allowed via the
    mobu config. This should be exposed via a Gafaelfawr anonymous ingress.
    """
    if config.github_refresh_app is None:
        raise RuntimeError("GitHub refresh app configuration is missing")
    webhook_secret = config.github_refresh_app.webhook_secret
    body = await context.request.body()
    event = Event.from_http(
        context.request.headers, body, secret=webhook_secret
    )

    owner = event.data.get("organization", {}).get("login")
    if owner not in config.github_refresh_app.accepted_github_orgs:
        context.logger.debug(
            "Ignoring GitHub event for unaccepted org",
            owner=owner,
            accepted_orgs=config.github_refresh_app.accepted_github_orgs,
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
    context.rebind_logger(
        github_delivery=event.delivery_id, github_app="refresh"
    )
    context.logger.debug("Received GitHub webhook", payload=event.data)
    # Give GitHub some time to reach internal consistency.
    await asyncio.sleep(GITHUB_WEBHOOK_WAIT_SECONDS)
    await gidgethub_router.dispatch(
        event=event,
        context=context,
    )


@gidgethub_router.register("push")
async def handle_push(event: Event, context: RequestContext) -> None:
    """Handle a push event."""
    push_event = GitHubPushEventModel.model_validate(event.data)
    ref = push_event.ref
    url = f"{push_event.repository.html_url}.git"
    context.rebind_logger(ref=ref, url=url)

    prefix, branch = ref.rsplit("/", 1)
    if prefix != "refs/heads":
        context.logger.debug(
            "github webhook ignored: ref is not a branch",
        )
        return

    flocks = context.manager.list_flocks_for_repo(
        repo_url=url, repo_ref=branch
    )
    if not flocks:
        context.logger.debug(
            "github webhook ignored: no flocks match repo and branch",
        )
        return

    for flock in flocks:
        context.manager.refresh_flock(flock)

    context.logger.info("github refresh webhook handled")
