"""Handlers for controlling users, ``/<app-name>/user/``."""

__all__ = [
    "post_user",
    "get_users",
    "get_user",
    "delete_user",
]

from aiohttp import web
from aiojobs.aiohttp import get_scheduler, spawn

from sciencemonkey.behavior import Idle
from sciencemonkey.handlers import routes
from sciencemonkey.user import User


@routes.post("/user")
async def post_user(request: web.Request) -> web.Response:
    """POST /user

    Create a user to use for load testing.  This takes all the
    required information to create a user, including username,
    uid, and other related fields that will be used in the ticket.
    """
    body = await request.json()
    logger = request.config_dict["safir/logger"]

    username = body["username"]
    uidnumber = body["uidnumber"]

    u = User(username, uidnumber)
    b = Idle(u)
    # logger.info(u)
    data = {"user": username}
    # logger.info(data)
    await spawn(request, b.run())
    return web.json_response(data)


@routes.get("/user")
async def get_users(request: web.Request) -> web.Response:
    """GET /user

    Get a list of all the users currently used for load testing.
    """
    data = []

    for b in get_scheduler(request):
        data.append(str(b))

    return web.json_response(data)


@routes.get("/user/{name}")
async def get_user(request: web.Request) -> web.Response:
    """GET /user/{name}

    Get info on a particular user.
    """
    username = request.match_info["name"]
    data = {"user": username}
    return web.json_response(data)


@routes.delete("/user/{name}")
async def delete_user(request: web.Request) -> web.Response:
    """DELETE /user/{name}

    Delete a particular user, which will cancel all testing it is doing.
    """
    username = request.match_info["name"]
    data = {"user": username}
    return web.json_response(data)
