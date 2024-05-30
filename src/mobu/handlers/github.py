"""Handlers for requests from GitHub, ``/mobu/github``."""

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends
from gidgethub.sansio import Event
from safir.slack.webhook import SlackRouteErrorHandler

from ..config import config
from ..constants import GITHUB_WEBHOOK_WAIT_SECONDS
from ..dependencies.context import RequestContext, anonymous_context_dependency
from .github_webhooks import webhook_router

github_router = APIRouter(route_class=SlackRouteErrorHandler)


@github_router.post(
    "/webhook",
    summary="GitHub webhooks",
    description="This endpoint receives webhook events from GitHub.",
    status_code=202,
)
async def post_github_webhook(
    context: Annotated[RequestContext, Depends(anonymous_context_dependency)],
) -> None:
    """Process GitHub webhook events.

    This should be exposed via a Gafaelfawr anonymous ingress.
    """
    webhook_secret = config.github_webhook_secret
    body = await context.request.body()
    event = Event.from_http(
        context.request.headers, body, secret=webhook_secret
    )

    # Bind the X-GitHub-Delivery header to the logger context; this
    # identifies the webhook request in GitHub's API and UI for
    # diagnostics
    context.rebind_logger(github_delivery=event.delivery_id)

    context.logger.debug("Received GitHub webhook", payload=event.data)
    # Give GitHub some time to reach internal consistency.
    await asyncio.sleep(GITHUB_WEBHOOK_WAIT_SECONDS)
    await webhook_router.dispatch(event=event, context=context)
