"""Tests for the NotebookRunner business."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import ANY

import pytest
from git import Actor, Repo

from tests.support.gafaelfawr import mock_gafaelfawr
from tests.support.util import wait_for_business

if TYPE_CHECKING:
    from aioresponses import aioresponses
    from httpx import AsyncClient

    from tests.support.slack import MockSlack


@pytest.mark.asyncio
async def test_run(
    client: AsyncClient, mock_aioresponses: aioresponses, tmp_path: Path
) -> None:
    mock_gafaelfawr(mock_aioresponses)

    # Set up a notebook repository.
    source_path = Path(__file__).parent.parent / "notebooks"
    repo_path = tmp_path / "notebooks"
    shutil.copytree(str(source_path), str(repo_path))
    os.remove(str(repo_path / "exception.ipynb"))
    repo = Repo.init(str(repo_path), initial_branch="main")
    for path in repo_path.iterdir():
        if not path.name.startswith("."):
            repo.index.add(str(path))
    actor = Actor("Someone", "someone@example.com")
    repo.index.commit("Initial commit", author=actor, committer=actor)

    # Start a monkey.
    r = await client.put(
        "/mobu/flocks",
        json={
            "name": "test",
            "count": 1,
            "user_spec": {"username_prefix": "testuser", "uid_start": 1000},
            "scopes": ["exec:notebook"],
            "options": {
                "spawn_settle_time": 0,
                "lab_settle_time": 0,
                "execution_idle_time": 0,
                "max_executions": 1,
                "repo_url": str(repo_path),
                "repo_branch": "main",
                "working_directory": str(repo_path),
            },
            "business": "NotebookRunner",
        },
    )
    assert r.status_code == 201

    # Wait until we've finished one loop and check the results.
    data = await wait_for_business(client, "testuser1")
    assert data == {
        "name": "testuser1",
        "business": {
            "failure_count": 0,
            "name": "NotebookRunner",
            "notebook": "test-notebook.ipynb",
            "success_count": 1,
            "timings": ANY,
        },
        "restart": False,
        "state": "RUNNING",
        "user": {
            "scopes": ["exec:notebook"],
            "token": ANY,
            "uidnumber": 1000,
            "username": "testuser1",
        },
    }

    # Get the log and check the cell output.
    r = await client.get("/mobu/flocks/test/monkeys/testuser1/log")
    assert r.status_code == 200
    assert "This is a test" in r.text
    assert "This is another test" in r.text
    assert "Final test" in r.text
    assert "Exception thrown" not in r.text


@pytest.mark.asyncio
async def test_alert(
    client: AsyncClient,
    slack: MockSlack,
    mock_aioresponses: aioresponses,
    tmp_path: Path,
) -> None:
    mock_gafaelfawr(mock_aioresponses)

    # Set up a notebook repository with the exception notebook.
    source_path = Path(__file__).parent.parent / "notebooks"
    repo_path = tmp_path / "notebooks"
    repo_path.mkdir()
    shutil.copy(str(source_path / "exception.ipynb"), str(repo_path))
    repo = Repo.init(str(repo_path), initial_branch="main")
    for path in repo_path.iterdir():
        if not path.name.startswith("."):
            repo.index.add(str(path))
    actor = Actor("Someone", "someone@example.com")
    repo.index.commit("Initial commit", author=actor, committer=actor)

    # The bad code run by the exception test.
    bad_code = 'foo = {"bar": "baz"}\nfoo["nothing"]'

    # Start a monkey.
    r = await client.put(
        "/mobu/flocks",
        json={
            "name": "test",
            "count": 1,
            "user_spec": {"username_prefix": "testuser", "uid_start": 1000},
            "scopes": ["exec:notebook"],
            "options": {
                "spawn_settle_time": 0,
                "lab_settle_time": 0,
                "execution_idle_time": 0,
                "max_executions": 1,
                "repo_url": str(repo_path),
                "repo_branch": "main",
            },
            "business": "NotebookRunner",
            "restart": True,
        },
    )
    assert r.status_code == 201

    # Wait until we've finished one loop and check the results.
    data = await wait_for_business(client, "testuser1")
    assert data == {
        "name": "testuser1",
        "business": {
            "failure_count": 1,
            "name": "NotebookRunner",
            "notebook": "exception.ipynb",
            "running_code": bad_code,
            "success_count": 0,
            "timings": ANY,
        },
        "restart": True,
        "state": "ERROR",
        "user": {
            "scopes": ["exec:notebook"],
            "token": ANY,
            "uidnumber": 1000,
            "username": "testuser1",
        },
    }

    # Check that an appropriate error was posted.
    assert slack.alerts == [
        {
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "Error while running `exception.ipynb`",
                    },
                },
                {
                    "type": "section",
                    "fields": [
                        {"type": "mrkdwn", "text": ANY},
                        {"type": "mrkdwn", "text": ANY},
                        {"type": "mrkdwn", "text": "*User*\ntestuser1"},
                        {"type": "mrkdwn", "text": "*Event*\nexecute_cell"},
                        {
                            "type": "mrkdwn",
                            "text": "*Cell id*\n`ed399c0a` (#2)",
                            "verbatim": True,
                        },
                        {"type": "mrkdwn", "text": "*Node*\nsome-node"},
                    ],
                },
            ],
            "attachments": [
                {
                    "blocks": [
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": ANY,
                                "verbatim": True,
                            },
                        },
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": (
                                    f"*Code executed*\n```\n{bad_code}\n```"
                                ),
                                "verbatim": True,
                            },
                        },
                    ]
                }
            ],
        }
    ]
    error = slack.alerts[0]["attachments"][0]["blocks"][0]["text"]["text"]
    assert "KeyError: 'nothing'" in error
