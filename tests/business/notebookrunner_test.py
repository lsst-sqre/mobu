"""Tests for the NotebookRunner business."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import cast
from unittest.mock import ANY

import pytest
import respx
from anys import ANY_AWARE_DATETIME_STR, AnyContains, AnySearch, AnyWithEntries
from httpx import AsyncClient
from rubin.nublado.client.testing import MockJupyter
from safir.metrics import NOT_NONE, MockEventPublisher
from safir.testing.sentry import Captured

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
    sentry_items: Captured,
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

    # Confirm Sentry errors
    (sentry_error,) = sentry_items.errors
    assert sentry_error["contexts"]["repo_info"] == {
        "repo_config_file": "PosixPath('mobu.yaml')",
        "repo_hash": ANY,
        "repo_ref": "main",
        "repo_url": AnySearch("test_invalid_repo_config0/notebooks$"),
    }
    assert sentry_error["exception"]["values"] == [
        AnyWithEntries(
            {
                "type": "ValidationError",
                "value": (AnySearch("2 validation errors for RepoConfig")),
            }
        ),
        AnyWithEntries(
            {
                "type": "RepositoryConfigError",
                "value": ("Error parsing config file: mobu.yaml"),
            }
        ),
    ]
    assert sentry_error["tags"] == {
        "business": "NotebookRunner",
        "flock": "test",
    }
    assert sentry_error["user"] == {"username": "bot-mobu-testuser1"}


@pytest.mark.asyncio
async def test_alert(
    client: AsyncClient,
    respx_mock: respx.Router,
    tmp_path: Path,
    events: Events,
    sentry_items: Captured,
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
        },
        "state": "ERROR",
        "user": {
            "scopes": ["exec:notebook"],
            "token": ANY,
            "username": "bot-mobu-testuser1",
        },
    }
    # Confirm Sentry errors
    (sentry_error,) = sentry_items.errors

    assert sentry_error["contexts"]["cell_info"] == {
        "code": 'foo = {"bar": "baz"}\nfoo["nothing"]',
        "cell_id": "ed399c0a",
        "cell_number": "#1",
    }
    assert sentry_error["contexts"]["notebook_filter_info"] == {
        "all": [AnySearch("/exception.ipynb$")],
        "excluded_by_dir": [],
        "excluded_by_requested": [],
        "excluded_by_service": [],
        "runnable": [AnySearch("/exception.ipynb$")],
    }
    assert sentry_error["contexts"]["notebook_info"] == {
        "iteration": "1/1",
        "notebook": "exception.ipynb",
    }
    assert sentry_error["contexts"]["phase"] == {
        "phase": "execute_cell",
        "started_at": ANY_AWARE_DATETIME_STR,
    }
    assert sentry_error["contexts"]["repo_info"] == {
        "repo_config_file": "PosixPath('mobu.yaml')",
        "repo_hash": ANY,
        "repo_ref": "main",
        "repo_url": AnySearch(r"/notebooks$"),
    }
    assert sentry_error["exception"]["values"] == AnyContains(
        AnyWithEntries(
            {
                "type": "NotebookCellExecutionError",
                "value": ("exception.ipynb: Error executing cell"),
            }
        )
    )
    assert sentry_error["tags"] == {
        "business": "NotebookRunner",
        "cell": "ed399c0a",
        "flock": "test",
        "image_description": "Recommended (Weekly 2077_43)",
        "image_reference": "lighthouse.ceres/library/sketchbook:recommended",
        "node": "Node1",
        "notebook": "exception.ipynb",
        "phase": "execute_cell",
    }
    assert sentry_error["user"] == {"username": "bot-mobu-testuser1"}

    (sentry_attachment,) = sentry_items.attachments
    assert sentry_attachment.filename == "nublado_error.txt"
    assert "KeyError: 'nothing'" in sentry_attachment.bytes.decode()

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
