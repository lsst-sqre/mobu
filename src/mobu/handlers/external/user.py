"""Handlers for controlling users, ``/<app-name>/user/``."""

__all__ = [
    "post_user",
    "get_users",
    "get_user",
    "delete_user",
]

import json
from datetime import datetime

from aiohttp import web

from mobu.handlers import routes
from mobu.monkeybusinessfactory import MonkeyBusinessFactory


@routes.post("/user")
async def post_user(request: web.Request) -> web.Response:
    """POST /user

    Create a user to use for load testing.  This takes all the
    required information to create a user, including username,
    uid, and other related fields that will be used in the ticket.
    """
    logger = request["safir/logger"]
    try:
        body = await request.json()
        logger.info(body)
        manager = request.config_dict["mobu/monkeybusinessmanager"]
        monkey = MonkeyBusinessFactory.create(body)
        await manager.manage_monkey(monkey)
        data = {"user": monkey.user.username}
        return web.json_response(data)
    except Exception:
        logger.exception(
            f"Unknown exception thrown while processing {request.url}"
        )
        raise


@routes.get("/user")
async def get_users(request: web.Request) -> web.Response:
    """GET /user

    Get a list of all the users currently used for load testing.
    """
    logger = request["safir/logger"]
    try:
        manager = request.config_dict["mobu/monkeybusinessmanager"]
        return web.json_response(manager.list_monkeys())
    except Exception:
        logger.exception(
            f"Unknown exception thrown while processing {request.url}"
        )
        raise


@routes.get("/user/{name}")
async def get_user(request: web.Request) -> web.Response:
    """GET /user/{name}

    Get info on a particular user.
    """
    logger = request["safir/logger"]
    try:
        username = request.match_info["name"]
        manager = request.config_dict["mobu/monkeybusinessmanager"]

        def json_dump(data: dict) -> str:
            return json.dumps(data, indent=4)

        try:
            monkey = manager.fetch_monkey(username)
            return web.json_response(monkey.dump(), dumps=json_dump)
        except KeyError:
            raise web.HTTPNotFound()
    except Exception:
        logger.exception(
            f"Unknown exception thrown while processing {request.url}"
        )
        raise


@routes.get("/user/{name}/log")
async def get_log(request: web.Request) -> web.FileResponse:
    """GET /user/{name}/log

    Retrieve the log for a particular user (and only that log).
    """
    logger = request["safir/logger"]
    try:
        username = request.match_info["name"]
        manager = request.config_dict["mobu/monkeybusinessmanager"]
        download_name = "-".join([username, str(datetime.now())])
        headers = {"Content-Disposition": f"filename={download_name}"}

        try:
            monkey = manager.fetch_monkey(username)
            return web.FileResponse(monkey.logfile(), headers=headers)
        except KeyError:
            raise web.HTTPNotFound()
    except Exception:
        logger.exception(
            f"Unknown exception thrown while processing {request.url}"
        )
        raise


@routes.delete("/user/{name}")
async def delete_user(request: web.Request) -> web.Response:
    """DELETE /user/{name}

    Delete a particular user, which will cancel all testing it is doing.
    """
    logger = request["safir/logger"]
    try:
        username = request.match_info["name"]
        manager = request.config_dict["mobu/monkeybusinessmanager"]
        await manager.release_monkey(username)
        return web.HTTPOk()
    except Exception:
        logger.exception(
            f"Unknown exception thrown while processing {request.url}"
        )
        raise
