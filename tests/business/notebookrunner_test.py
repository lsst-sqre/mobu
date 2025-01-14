"""Tests for the NotebookRunner business."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import cast
from unittest.mock import ANY

import pytest
import respx
from anys import AnySearch
from httpx import AsyncClient
from rubin.nublado.client.testing import MockJupyter
from safir.metrics import NOT_NONE, MockEventPublisher
from safir.testing.slack import MockSlackWebhook

from mobu.events import Events
from mobu.storage.git import Git

from ..support.constants import TEST_DATA_DIR
from ..support.gafaelfawr import mock_gafaelfawr
from ..support.util import wait_for_business, wait_for_log_message


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


@pytest.mark.asyncio
async def test_run(
    client: AsyncClient,
    respx_mock: respx.Router,
    tmp_path: Path,
    events: Events,
) -> None:
    mock_gafaelfawr(respx_mock)
    cwd = Path.cwd()

    # Set up a notebook repository.
    source_path = TEST_DATA_DIR / "notebooks"
    repo_path = tmp_path / "notebooks"

    shutil.copytree(str(source_path), str(repo_path))

    # Set up git repo
    repo_hash = await setup_git_repo(repo_path)

    # Start a monkey. We have to do this in a try/finally block since the
    # runner will change working directories, which because working
    # directories are process-global may mess up future tests.
    try:
        r = await client.put(
            "/mobu/flocks",
            json={
                "name": "test",
                "count": 1,
                "user_spec": {"username_prefix": "bot-mobu-testuser"},
                "scopes": ["exec:notebook"],
                "business": {
                    "type": "NotebookRunner",
                    "options": {
                        "spawn_settle_time": 0,
                        "execution_idle_time": 0,
                        "max_executions": 1,
                        "repo_url": str(repo_path),
                        "repo_ref": "main",
                        "working_directory": str(repo_path),
                    },
                },
            },
        )
        assert r.status_code == 201

        # Wait until we've finished one loop and check the results.
        data = await wait_for_business(client, "bot-mobu-testuser1")
        assert data == {
            "name": "bot-mobu-testuser1",
            "business": {
                "failure_count": 0,
                "name": "NotebookRunner",
                "notebook": "test-notebook.ipynb",
                "refreshing": False,
                "success_count": 1,
                "timings": ANY,
            },
            "state": "RUNNING",
            "user": {
                "scopes": ["exec:notebook"],
                "token": ANY,
                "username": "bot-mobu-testuser1",
            },
        }
    finally:
        os.chdir(cwd)

    # Get the log and check the cell output.
    r = await client.get("/mobu/flocks/test/monkeys/bot-mobu-testuser1/log")
    assert r.status_code == 200

    # Root notebook
    assert "This is a test" in r.text
    assert "This is another test" in r.text
    assert "Final test" in r.text

    # Exceptions
    assert "Exception thrown" not in r.text

    # Make sure mobu ran all of the notebooks it thinks it should have
    assert "Done with this cycle of notebooks" in r.text

    # Check events
    common = {
        "business": "NotebookRunner",
        "duration": NOT_NONE,
        "flock": "test",
        "notebook": AnySearch("test-notebook.ipynb$"),
        "repo": AnySearch("/notebooks$"),
        "repo_ref": "main",
        "repo_hash": repo_hash,
        "success": True,
        "username": "bot-mobu-testuser1",
    }
    pub_notebook = cast(
        MockEventPublisher, events.notebook_execution
    ).published
    pub_notebook.assert_published_all([common])

    pub_cell = cast(
        MockEventPublisher,
        events.notebook_cell_execution,
    ).published
    pub_cell.assert_published_all(
        [
            item | common
            for item in [
                {"cell_id": "f84f0959"},
                {"cell_id": "44ada997"},
                {"cell_id": "53a941a4"},
                {"cell_id": "823560c6"},
            ]
        ]
    )


@pytest.mark.asyncio
async def test_run_debug_log(
    client: AsyncClient, respx_mock: respx.Router, tmp_path: Path
) -> None:
    mock_gafaelfawr(respx_mock)
    cwd = Path.cwd()

    # Set up a notebook repository.
    source_path = TEST_DATA_DIR / "notebooks"
    repo_path = tmp_path / "notebooks"

    shutil.copytree(str(source_path), str(repo_path))

    # Set up git repo
    await setup_git_repo(repo_path)

    # Start a monkey. We have to do this in a try/finally block since the
    # runner will change working directories, which because working
    # directories are process-global may mess up future tests.
    try:
        r = await client.put(
            "/mobu/flocks",
            json={
                "name": "test",
                "count": 1,
                "user_spec": {"username_prefix": "bot-mobu-testuser"},
                "scopes": ["exec:notebook"],
                "business": {
                    "type": "NotebookRunner",
                    "options": {
                        "log_level": "DEBUG",
                        "spawn_settle_time": 0,
                        "execution_idle_time": 0,
                        "max_executions": 1,
                        "repo_url": str(repo_path),
                        "repo_ref": "main",
                        "working_directory": str(repo_path),
                    },
                },
            },
        )
        assert r.status_code == 201

        # Wait until we've finished one loop and check the results.
        data = await wait_for_business(client, "bot-mobu-testuser1")
        assert data == {
            "name": "bot-mobu-testuser1",
            "business": {
                "failure_count": 0,
                "name": "NotebookRunner",
                "notebook": "test-notebook.ipynb",
                "refreshing": False,
                "success_count": 1,
                "timings": ANY,
            },
            "state": "RUNNING",
            "user": {
                "scopes": ["exec:notebook"],
                "token": ANY,
                "username": "bot-mobu-testuser1",
            },
        }
    finally:
        os.chdir(cwd)

    # Get the log and check the cell output.
    r = await client.get("/mobu/flocks/test/monkeys/bot-mobu-testuser1/log")
    assert r.status_code == 200
    # Only occurs in the debug log.
    assert "Set _hub_xsrf" in r.text


@pytest.mark.asyncio
async def test_run_recursive(
    client: AsyncClient,
    respx_mock: respx.Router,
    tmp_path: Path,
    events: Events,
) -> None:
    mock_gafaelfawr(respx_mock)
    cwd = Path.cwd()

    # Set up a notebook repository.
    source_path = TEST_DATA_DIR / "notebooks_recursive"
    repo_path = tmp_path / "notebooks"

    shutil.copytree(str(source_path), str(repo_path))
    # Remove exception notebook
    (repo_path / "exception.ipynb").unlink()

    # Set up git repo
    repo_hash = await setup_git_repo(repo_path)

    # Start a monkey. We have to do this in a try/finally block since the
    # runner will change working directories, which because working
    # directories are process-global may mess up future tests.
    try:
        r = await client.put(
            "/mobu/flocks",
            json={
                "name": "test",
                "count": 1,
                "user_spec": {"username_prefix": "bot-mobu-testuser"},
                "scopes": ["exec:notebook"],
                "business": {
                    "type": "NotebookRunner",
                    "options": {
                        "spawn_settle_time": 0,
                        "execution_idle_time": 0,
                        "max_executions": 4,
                        "repo_url": str(repo_path),
                        "repo_ref": "main",
                        "working_directory": str(repo_path),
                    },
                },
            },
        )
        assert r.status_code == 201

        # Wait until we've finished one loop and check the results.
        data = await wait_for_business(client, "bot-mobu-testuser1")
        assert data == {
            "name": "bot-mobu-testuser1",
            "business": {
                "failure_count": 0,
                "name": "NotebookRunner",
                "notebook": ANY,
                "refreshing": False,
                "success_count": 1,
                "timings": ANY,
            },
            "state": "RUNNING",
            "user": {
                "scopes": ["exec:notebook"],
                "token": ANY,
                "username": "bot-mobu-testuser1",
            },
        }
    finally:
        os.chdir(cwd)

    # Get the log and check the cell output.
    r = await client.get("/mobu/flocks/test/monkeys/bot-mobu-testuser1/log")
    assert r.status_code == 200

    # Root notebook
    assert "This is a test" in r.text
    assert "This is another test" in r.text
    assert "Final test" in r.text

    # some-dir notebook
    assert "Test some-dir" in r.text
    assert "Another test some-dir" in r.text
    assert "Final test some-dir" in r.text

    # some-other-dir notebook
    assert "Test some-other-dir" in r.text
    assert "Another test some-other-dir" in r.text
    assert "Final test some-other-dir" in r.text

    # double-nested-dir notebook
    assert "Test double-nested-dir" in r.text
    assert "Another test double-nested-dir" in r.text
    assert "Final test double-nested-dir" in r.text

    # Exceptions
    assert "Exception thrown" not in r.text

    # Make sure mobu ran all of the notebooks it thinks it should have
    assert "Done with this cycle of notebooks" in r.text

    # Check events
    common = {
        "business": "NotebookRunner",
        "duration": NOT_NONE,
        "flock": "test",
        "repo": AnySearch("/notebooks$"),
        "repo_ref": "main",
        "repo_hash": repo_hash,
        "success": True,
        "username": "bot-mobu-testuser1",
    }
    published = cast(MockEventPublisher, events.notebook_execution).published
    published.assert_published_all(
        [
            item | common
            for item in [
                {
                    "notebook": AnySearch("test-some-other-dir.ipynb$"),
                },
                {
                    "notebook": AnySearch("test-some-dir-notebook.ipynb$"),
                },
                {
                    "notebook": AnySearch("test-notebook.ipynb$"),
                },
                {
                    "notebook": AnySearch("test-double-nested-dir.ipynb$"),
                },
            ]
        ],
        any_order=True,
    )


@pytest.mark.asyncio
async def test_run_required_services(
    client: AsyncClient, respx_mock: respx.Router, tmp_path: Path
) -> None:
    mock_gafaelfawr(respx_mock)
    cwd = Path.cwd()

    # Set up a notebook repository.
    source_path = TEST_DATA_DIR / "notebooks_services"
    repo_path = tmp_path / "notebooks"

    shutil.copytree(str(source_path), str(repo_path))

    # Set up git repo
    await setup_git_repo(repo_path)

    # Start a monkey. We have to do this in a try/finally block since the
    # runner will change working directories, which because working
    # directories are process-global may mess up future tests.
    try:
        r = await client.put(
            "/mobu/flocks",
            json={
                "name": "test",
                "count": 1,
                "user_spec": {"username_prefix": "bot-mobu-testuser"},
                "scopes": ["exec:notebook"],
                "business": {
                    "type": "NotebookRunner",
                    "options": {
                        "spawn_settle_time": 0,
                        "execution_idle_time": 0,
                        "max_executions": 2,
                        "repo_url": str(repo_path),
                        "repo_ref": "main",
                        "working_directory": str(repo_path),
                    },
                },
            },
        )
        assert r.status_code == 201

        # Wait until we've finished one loop and check the results.
        data = await wait_for_business(client, "bot-mobu-testuser1")
        assert data == {
            "name": "bot-mobu-testuser1",
            "business": {
                "failure_count": 0,
                "name": "NotebookRunner",
                "notebook": ANY,
                "refreshing": False,
                "success_count": 1,
                "timings": ANY,
            },
            "state": "RUNNING",
            "user": {
                "scopes": ["exec:notebook"],
                "token": ANY,
                "username": "bot-mobu-testuser1",
            },
        }
    finally:
        os.chdir(cwd)

    # Get the log and check the cell output.
    r = await client.get("/mobu/flocks/test/monkeys/bot-mobu-testuser1/log")
    assert r.status_code == 200

    # Notebooks with all services available
    assert "Required services are available" in r.text
    assert "Required services are available - some-dir" in r.text
    assert "Final test" in r.text

    # Notebook with missing services
    assert "Required services are NOT available" not in r.text

    # Make sure mobu ran all of the notebooks it thinks it should have
    assert "Done with this cycle of notebooks" in r.text


@pytest.mark.asyncio
async def test_run_all_notebooks(
    client: AsyncClient, respx_mock: respx.Router, tmp_path: Path
) -> None:
    mock_gafaelfawr(respx_mock)
    cwd = Path.cwd()

    # Set up a notebook repository.
    source_path = TEST_DATA_DIR / "notebooks_services"
    repo_path = tmp_path / "notebooks"

    shutil.copytree(str(source_path), str(repo_path))

    # Exclude some notebooks
    (repo_path / "mobu.yaml").write_text('exclude_dirs: ["some-dir"]')

    # Set up git repo
    await setup_git_repo(repo_path)

    # Start a monkey. We have to do this in a try/finally block since the
    # runner will change working directories, which because working
    # directories are process-global may mess up future tests.
    try:
        # Note `max_executions` is not declared here, `notebooks_to_run` is
        # declared instead.
        r = await client.put(
            "/mobu/flocks",
            json={
                "name": "test",
                "count": 1,
                "user_spec": {"username_prefix": "bot-mobu-testuser"},
                "scopes": ["exec:notebook"],
                "business": {
                    "type": "NotebookRunner",
                    "options": {
                        "spawn_settle_time": 0,
                        "execution_idle_time": 0,
                        "repo_url": str(repo_path),
                        "repo_ref": "main",
                        "notebooks_to_run": [
                            "test-notebook-has-services.ipynb",
                            # This shouldn't run because services are missing
                            "test-notebook-missing-service.ipynb",
                            # This shouldn't run because the dir is excluded
                            "some-dir/test-other-notebook-has-services.ipynb",
                        ],
                        "working_directory": str(repo_path),
                    },
                },
            },
        )
        assert r.status_code == 201

        # Wait until we've finished one loop and check the results.
        data = await wait_for_business(client, "bot-mobu-testuser1")
        assert data == {
            "name": "bot-mobu-testuser1",
            "business": {
                "failure_count": 0,
                "name": "NotebookRunner",
                "notebook": "test-notebook-has-services.ipynb",
                "refreshing": False,
                "success_count": 1,
                "timings": ANY,
            },
            "state": "RUNNING",
            "user": {
                "scopes": ["exec:notebook"],
                "token": ANY,
                "username": "bot-mobu-testuser1",
            },
        }
    finally:
        os.chdir(cwd)

    # Get the log and check the cell output.
    r = await client.get("/mobu/flocks/test/monkeys/bot-mobu-testuser1/log")
    assert r.status_code == 200

    # Notebooks with all services available
    assert "Required services are available" in r.text
    assert "Final test" in r.text

    # Should have been excluded by dir
    assert "Required services are available - some-dir" not in r.text

    # Notebook with missing services
    assert "Required services are NOT available" not in r.text

    # Make sure mobu ran all of the notebooks it thinks it should have
    assert "Done with this cycle of notebooks" in r.text


@pytest.mark.asyncio
async def test_refresh(
    client: AsyncClient,
    jupyter: MockJupyter,
    respx_mock: respx.Router,
    tmp_path: Path,
) -> None:
    mock_gafaelfawr(respx_mock)
    cwd = Path.cwd()

    # Set up a notebook repository.
    source_path = TEST_DATA_DIR / "notebooks"
    repo_path = tmp_path / "notebooks"

    shutil.copytree(str(source_path), str(repo_path))

    # Set up git repo
    await setup_git_repo(repo_path)

    # Start a monkey. We have to do this in a try/finally block since the
    # runner will change working directories, which because working
    # directories are process-global may mess up future tests.
    try:
        r = await client.put(
            "/mobu/flocks",
            json={
                "name": "test",
                "count": 1,
                "user_spec": {"username_prefix": "bot-mobu-testuser"},
                "scopes": ["exec:notebook"],
                "business": {
                    "type": "NotebookRunner",
                    "options": {
                        "spawn_settle_time": 0,
                        "execution_idle_time": 1,
                        "idle_time": 1,
                        "max_executions": 1000,
                        "repo_url": str(repo_path),
                        "repo_ref": "main",
                        "working_directory": str(repo_path),
                    },
                },
            },
        )
        assert r.status_code == 201

        # We should see a message from the notebook execution in the logs.
        assert await wait_for_log_message(
            client, "bot-mobu-testuser1", msg="This is a test"
        )

        # Change the notebook and git commit it
        notebook = repo_path / "test-notebook.ipynb"
        contents = notebook.read_text()
        new_contents = contents.replace("This is a test", "This is a NEW test")
        notebook.write_text(new_contents)

        git = Git(repo=repo_path)
        await git.add(str(notebook))
        await git.commit("-m", "Updating notebook")

        jupyter.expected_session_name = "test-notebook.ipynb"
        jupyter.expected_session_type = "notebook"

        # Refresh the notebook
        r = await client.post("/mobu/flocks/test/refresh")
        assert r.status_code == 202

        # The refresh should have forced a new execution
        assert await wait_for_log_message(
            client, "bot-mobu-testuser1", msg="Deleting lab"
        )

        # We should see a message from the updated notebook.
        assert await wait_for_log_message(
            client, "bot-mobu-testuser1", msg="This is a NEW test"
        )
    finally:
        os.chdir(cwd)


@pytest.mark.asyncio
async def test_exclude_dirs(
    client: AsyncClient, respx_mock: respx.Router, tmp_path: Path
) -> None:
    mock_gafaelfawr(respx_mock)
    cwd = Path.cwd()

    # Set up a notebook repository.
    source_path = TEST_DATA_DIR / "notebooks_recursive"
    repo_path = tmp_path / "notebooks"

    shutil.copytree(str(source_path), str(repo_path))
    # Remove exception notebook
    (repo_path / "exception.ipynb").unlink()

    # Add a config file
    (repo_path / "mobu.yaml").write_text('exclude_dirs: ["some-other-dir"]')

    # Set up git repo
    await setup_git_repo(repo_path)

    # Start a monkey. We have to do this in a try/finally block since the
    # runner will change working directories, which because working
    # directories are process-global may mess up future tests.
    try:
        r = await client.put(
            "/mobu/flocks",
            json={
                "name": "test",
                "count": 1,
                "user_spec": {"username_prefix": "bot-mobu-testuser"},
                "scopes": ["exec:notebook"],
                "business": {
                    "type": "NotebookRunner",
                    "options": {
                        "spawn_settle_time": 0,
                        "execution_idle_time": 0,
                        "max_executions": 2,
                        "repo_url": str(repo_path),
                        "repo_ref": "main",
                        "working_directory": str(repo_path),
                    },
                },
            },
        )
        assert r.status_code == 201

        # Wait until we've finished one loop and check the results.
        data = await wait_for_business(client, "bot-mobu-testuser1")
        assert data == {
            "name": "bot-mobu-testuser1",
            "business": {
                "failure_count": 0,
                "name": "NotebookRunner",
                "notebook": ANY,
                "refreshing": False,
                "success_count": 1,
                "timings": ANY,
            },
            "state": "RUNNING",
            "user": {
                "scopes": ["exec:notebook"],
                "token": ANY,
                "username": "bot-mobu-testuser1",
            },
        }
    finally:
        os.chdir(cwd)

    # Get the log and check the cell output.
    r = await client.get("/mobu/flocks/test/monkeys/bot-mobu-testuser1/log")
    assert r.status_code == 200

    # Root notebook
    assert "This is a test" in r.text
    assert "This is another test" in r.text
    assert "Final test" in r.text

    # some-other-dir notebook
    assert "Test some-other-dir" not in r.text
    assert "Another test some-other-dir" not in r.text
    assert "Final test some-other-dir" not in r.text

    # some-dir notebook
    assert "Test some-dir" in r.text

    # nested-dir notebook
    assert "Test double-nested-dir" not in r.text

    # Exceptions
    assert "Exception thrown" not in r.text

    # Make sure mobu ran all of the notebooks it thinks it should have
    assert "Done with this cycle of notebooks" in r.text


@pytest.mark.asyncio
async def test_invalid_repo_config(
    client: AsyncClient,
    respx_mock: respx.Router,
    tmp_path: Path,
    slack: MockSlackWebhook,
) -> None:
    mock_gafaelfawr(respx_mock)
    cwd = Path.cwd()

    # Set up a notebook repository.
    source_path = TEST_DATA_DIR / "notebooks_recursive"
    repo_path = tmp_path / "notebooks"

    shutil.copytree(str(source_path), str(repo_path))
    # Remove exception notebook
    (repo_path / "exception.ipynb").unlink()

    # Add a bad config file
    (repo_path / "mobu.yaml").write_text(
        'exclude_dirs: "blah"\nsome_other_key: "whatever"'
    )

    # Set up git repo
    await setup_git_repo(repo_path)

    # Start a monkey. We have to do this in a try/finally block since the
    # runner will change working directories, which because working
    # directories are process-global may mess up future tests.
    try:
        r = await client.put(
            "/mobu/flocks",
            json={
                "name": "test",
                "count": 1,
                "user_spec": {"username_prefix": "bot-mobu-testuser"},
                "scopes": ["exec:notebook"],
                "business": {
                    "type": "NotebookRunner",
                    "options": {
                        "spawn_settle_time": 0,
                        "execution_idle_time": 0,
                        "max_executions": 2,
                        "repo_url": str(repo_path),
                        "repo_ref": "main",
                        "working_directory": str(repo_path),
                    },
                },
            },
        )
        assert r.status_code == 201

        # Wait until we've finished one loop and check the results.
        data = await wait_for_business(client, "bot-mobu-testuser1")
        assert data == {
            "business": {
                "failure_count": 1,
                "name": "NotebookRunner",
                "refreshing": False,
                "success_count": 0,
                "timings": ANY,
            },
            "name": "bot-mobu-testuser1",
            "state": "STOPPING",
            "user": {
                "scopes": ["exec:notebook"],
                "token": ANY,
                "username": "bot-mobu-testuser1",
            },
        }
    finally:
        os.chdir(cwd)

    # Make sure we sent a validation error in a Slack notification
    assert slack.messages == [
        {
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "Error parsing config file: mobu.yaml",
                        "verbatim": True,
                    },
                },
                {
                    "type": "section",
                    "fields": [
                        {
                            "type": "mrkdwn",
                            "text": ANY,
                            "verbatim": True,
                        },
                        {
                            "type": "mrkdwn",
                            "text": "*Exception type*\nRepositoryConfigError",
                            "verbatim": True,
                        },
                        {
                            "type": "mrkdwn",
                            "text": "*User*\nbot-mobu-testuser1",
                            "verbatim": True,
                        },
                        {
                            "type": "mrkdwn",
                            "text": "*Monkey*\ntest/bot-mobu-testuser1",
                            "verbatim": True,
                        },
                    ],
                },
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
                        "text": "*Git Ref*\nmain",
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
                        }
                    ]
                }
            ],
        }
    ]

    repo = slack.messages[0]["blocks"][2]["text"]["text"]
    assert "test_invalid_repo_config0/notebooks" in repo

    error = slack.messages[0]["attachments"][0]["blocks"][0]["text"]["text"]
    assert "ValidationError:" in error
    assert "2 validation errors for RepoConfig" in error


@pytest.mark.asyncio
async def test_alert(
    client: AsyncClient,
    slack: MockSlackWebhook,
    respx_mock: respx.Router,
    tmp_path: Path,
    events: Events,
) -> None:
    mock_gafaelfawr(respx_mock)

    # Set up a notebook repository with the exception notebook.
    source_path = TEST_DATA_DIR / "notebooks_recursive"
    repo_path = tmp_path / "notebooks"
    repo_path.mkdir()
    shutil.copy(str(source_path / "exception.ipynb"), str(repo_path))

    # Set up git repo
    repo_hash = await setup_git_repo(repo_path)

    # The bad code run by the exception test.
    bad_code = 'foo = {"bar": "baz"}\nfoo["nothing"]'

    # Start a monkey.
    r = await client.put(
        "/mobu/flocks",
        json={
            "name": "test",
            "count": 1,
            "user_spec": {"username_prefix": "bot-mobu-testuser"},
            "scopes": ["exec:notebook"],
            "business": {
                "type": "NotebookRunner",
                "restart": True,
                "options": {
                    "spawn_settle_time": 0,
                    "execution_idle_time": 0,
                    "max_executions": 1,
                    "repo_url": str(repo_path),
                    "repo_ref": "main",
                },
            },
        },
    )
    assert r.status_code == 201

    # Wait until we've finished one loop and check the results.
    data = await wait_for_business(client, "bot-mobu-testuser1")
    assert data == {
        "name": "bot-mobu-testuser1",
        "business": {
            "failure_count": 1,
            "image": {
                "description": ANY,
                "reference": ANY,
            },
            "name": "NotebookRunner",
            "notebook": "exception.ipynb",
            "refreshing": False,
            "running_code": bad_code,
            "success_count": 0,
            "timings": ANY,
        },
        "state": "ERROR",
        "user": {
            "scopes": ["exec:notebook"],
            "token": ANY,
            "username": "bot-mobu-testuser1",
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
                        "text": (
                            "Error while running `exception.ipynb`"
                            " cell `ed399c0a`"
                        ),
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
                            "text": "*User*\nbot-mobu-testuser1",
                            "verbatim": True,
                        },
                        {
                            "type": "mrkdwn",
                            "text": "*Image*\nRecommended (Weekly 2077_43)",
                            "verbatim": True,
                        },
                        {
                            "type": "mrkdwn",
                            "text": "*Event*\nexecute_code",
                            "verbatim": True,
                        },
                        {
                            "type": "mrkdwn",
                            "text": "*Monkey*\ntest/bot-mobu-testuser1",
                            "verbatim": True,
                        },
                    ],
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "*Node*\nNode1",
                        "verbatim": True,
                    },
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": (
                            "*Cell*\n`exception.ipynb` cell `ed399c0a` (#1)"
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

    # Check events
    common = {
        "business": "NotebookRunner",
        "duration": NOT_NONE,
        "flock": "test",
        "notebook": AnySearch("exception.ipynb"),
        "repo": AnySearch("/notebooks"),
        "repo_ref": "main",
        "repo_hash": repo_hash,
        "username": "bot-mobu-testuser1",
    }
    pub_notebook = cast(
        MockEventPublisher, events.notebook_execution
    ).published
    pub_notebook.assert_published_all([{"success": False} | common])

    pub_cell = cast(
        MockEventPublisher,
        events.notebook_cell_execution,
    ).published
    pub_cell.assert_published_all(
        [common | {"cell_id": "ed399c0a", "success": False}]
    )
