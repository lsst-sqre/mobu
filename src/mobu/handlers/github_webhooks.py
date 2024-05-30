"""Github webhook handlers."""

from gidgethub import routing
from gidgethub.sansio import Event

from ..dependencies.context import RequestContext

__all__ = ["webhook_router"]

webhook_router = routing.Router()


@webhook_router.register("push")
async def handle_push(event: Event, context: RequestContext) -> None:
    """Handle a push event."""
    ref = event.data["ref"]
    url = event.data["repository"]["clone_url"]
    context.rebind_logger(ref=ref, url=url)

    prefix, branch = ref.rsplit("/", 1)
    if prefix != "refs/heads":
        context.logger.debug(
            "github webhook ignored: ref is not a branch",
        )
        return

    flocks = context.manager.list_flocks_for_repo(
        repo_url=url, repo_branch=branch
    )
    if not flocks:
        context.logger.debug(
            "github webhook ignored: no flocks match repo and branch",
        )
        return

    for flock in flocks:
        context.manager.refresh_flock(flock)

    context.logger.info("github webhook handled")
