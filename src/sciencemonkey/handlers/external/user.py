"""Handlers for controlling users, ``/<app-name>/user/``."""

__all__ = [
    "post_user",
    "get_users",
    "get_user",
    "delete_user",
]

from aiohttp import web
from aiojobs.aiohttp import spawn

from sciencemonkey.behavior import Idle
from sciencemonkey.handlers import routes
from sciencemonkey.user import User

active_users = dict()


@routes.post("/user")
async def post_user(request: web.Request) -> web.Response:
    """POST /user

    Create a user to use for load testing.  This takes all the
    required information to create a user, including username,
    uid, and other related fields that will be used in the ticket.
    """
    body = await request.json()
    logger = request["safir/logger"]
    logger.info(body)

    username = body["username"]
    uidnumber = body["uidnumber"]

    u = User(username, uidnumber)
    b = Idle(u)

    active_users[username] = b
    b.job = await spawn(request, b.run())

    data = {"user": username}
    return web.json_response(data)


@routes.get("/user")
async def get_users(request: web.Request) -> web.Response:
    """GET /user

    Get a list of all the users currently used for load testing.
    """
    data = []

    for username, behavior in active_users.items():
        data.append(username)

    return web.json_response(data)


@routes.get("/user/{name}")
async def get_user(request: web.Request) -> web.Response:
    """GET /user/{name}

    Get info on a particular user.
    """
    username = request.match_info["name"]

    if username not in active_users:
        raise web.HTTPNotFound()

    behavior = active_users[username]
    data = {"user": username, "behavior": str(behavior)}
    return web.json_response(data)


@routes.delete("/user/{name}")
async def delete_user(request: web.Request) -> web.Response:
    """DELETE /user/{name}

    Delete a particular user, which will cancel all testing it is doing.
    """
    username = request.match_info["name"]

    if username in active_users:
        behavior = active_users[username]
        await behavior.job.close()
        del active_users[username]

    return web.HTTPOk()
