"""Utility functions for tests."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from httpx import AsyncClient

from mobu.storage.git import Git

__all__ = [
    "wait_for_business",
    "wait_for_log_message",
]


async def wait_for_business(
    client: AsyncClient, username: str, *, flock: str = "test"
) -> dict[str, Any]:
    """Wait for one loop of business to complete and return its data."""
    for _ in range(1, 10):
        await asyncio.sleep(0.5)
        r = await client.get(f"/mobu/flocks/{flock}/monkeys/{username}")
        assert r.status_code == 200
        data = r.json()
        if data["business"]["success_count"] > 0:
            break
        if data["business"]["failure_count"] > 0:
            break
    return data


async def wait_for_log_message(
    client: AsyncClient, username: str, *, flock: str = "test", msg: str
) -> bool:
    """Wait until some text appears in a user's log."""
    for _ in range(1, 10):
        await asyncio.sleep(0.5)
        r = await client.get(f"/mobu/flocks/{flock}/monkeys/{username}/log")
        assert r.status_code == 200
        if msg in r.text:
            return True
    return False


async def wait_for_flock_start(client: AsyncClient, flock: str) -> None:
    """Wait for all the monkeys in a flock to have started."""
    for _ in range(1, 10):
        await asyncio.sleep(0.5)
        r = await client.get(f"/mobu/flocks/{flock}")
        assert r.status_code == 200
        data = r.json()
        good = True
        for monkey in data["monkeys"]:
            if monkey["state"] != "RUNNING":
                good = False
        if good:
            break


async def setup_git_repo(repo_path: Path) -> str:
    """Initialize and populate a git repo at `repo_path`.

    Returns
    -------
    str
        Commit hash of the cloned repo
    """
    git = Git(repo=repo_path)
    await git.init("--initial-branch=main")
    await git.config("user.email", "gituser@example.com")
    await git.config("user.name", "Git User")
    for path in repo_path.iterdir():
        if not path.name.startswith("."):
            await git.add(str(path))
    await git.commit("-m", "Initial commit")
    return await git.repo_hash()
