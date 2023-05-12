"""Tests for the NotebookRunner business."""

from __future__ import annotations

import shutil
from pathlib import Path
from unittest.mock import ANY

import pytest
import respx
from git.repo import Repo
from git.util import Actor
from httpx import AsyncClient
from safir.testing.slack import MockSlackWebhook

from ..support.gafaelfawr import mock_gafaelfawr
from ..support.util import wait_for_business


@pytest.mark.asyncio
async def test_run(
    client: AsyncClient, respx_mock: respx.Router, tmp_path: Path
) -> None:
    mock_gafaelfawr(respx_mock)

    # Set up a notebook repository.
    source_path = Path(__file__).parent.parent / "notebooks"
    repo_path = tmp_path / "notebooks"
    shutil.copytree(str(source_path), str(repo_path))
    (repo_path / "exception.ipynb").unlink()
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
            "user_spec": {"username_prefix": "testuser"},
            "scopes": ["exec:notebook"],
            "business": {
                "type": "NotebookRunner",
                "options": {
                    "spawn_settle_time": 0,
                    "execution_idle_time": 0,
                    "max_executions": 1,
                    "repo_url": str(repo_path),
                    "repo_branch": "main",
                    "working_directory": str(repo_path),
                },
            },
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
        "state": "RUNNING",
        "user": {
            "scopes": ["exec:notebook"],
            "token": ANY,
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
    slack: MockSlackWebhook,
    respx_mock: respx.Router,
    tmp_path: Path,
) -> None:
    mock_gafaelfawr(respx_mock)

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
            "user_spec": {"username_prefix": "testuser"},
            "scopes": ["exec:notebook"],
            "business": {
                "type": "NotebookRunner",
                "restart": True,
                "options": {
                    "spawn_settle_time": 0,
                    "execution_idle_time": 0,
                    "max_executions": 1,
                    "repo_url": str(repo_path),
                    "repo_branch": "main",
                },
            },
        },
    )
    assert r.status_code == 201

    # Wait until we've finished one loop and check the results.
    data = await wait_for_business(client, "testuser1")
    assert data == {
        "name": "testuser1",
        "business": {
            "failure_count": 1,
            "image": {
                "description": "Recommended (Weekly 2077_43)",
                "reference": (
                    "lighthouse.ceres/library/sketchbook:recommended"
                ),
            },
            "name": "NotebookRunner",
            "notebook": "exception.ipynb",
            "running_code": bad_code,
            "success_count": 0,
            "timings": ANY,
        },
        "state": "ERROR",
        "user": {
            "scopes": ["exec:notebook"],
            "token": ANY,
            "username": "testuser1",
        },
    }

    # Check that an appropriate error was posted.
    assert slack.messages == [
        {
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "Error while running `exception.ipynb`",
                        "verbatim": True,
                    },
                },
                {
                    "type": "section",
                    "fields": [
                        {"type": "mrkdwn", "text": ANY, "verbatim": True},
                        {"type": "mrkdwn", "text": ANY, "verbatim": True},
                        {
                            "type": "mrkdwn",
                            "text": "*Exception type*\nCodeExecutionError",
                            "verbatim": True,
                        },
                        {
                            "type": "mrkdwn",
                            "text": "*User*\ntestuser1",
                            "verbatim": True,
                        },
                        {
                            "type": "mrkdwn",
                            "text": "*Event*\nexecute_cell",
                            "verbatim": True,
                        },
                        {
                            "type": "mrkdwn",
                            "text": "*Image*\nRecommended (Weekly 2077_43)",
                            "verbatim": True,
                        },
                    ],
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "*Node*\nsome-node",
                        "verbatim": True,
                    },
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": (
                            "*Cell*\n`exception.ipynb` cell `ed399c0a` (#2)"
                        ),
                        "verbatim": True,
                    },
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
    error = slack.messages[0]["attachments"][0]["blocks"][0]["text"]["text"]
    assert "KeyError: 'nothing'" in error
