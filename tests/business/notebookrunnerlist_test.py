"""Tests for the NotebookRunnerList business."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from unittest.mock import ANY

import pytest
import respx
from httpx import AsyncClient

from ..support.constants import TEST_DATA_DIR
from ..support.gafaelfawr import mock_gafaelfawr
from ..support.util import setup_git_repo, wait_for_business

# Use the Jupyter mock for all tests in this file.
pytestmark = pytest.mark.usefixtures("jupyter")


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
        # Note `max_executions` is not declared here
        r = await client.put(
            "/mobu/flocks",
            json={
                "name": "test",
                "count": 1,
                "user_spec": {"username_prefix": "bot-mobu-testuser"},
                "scopes": ["exec:notebook"],
                "business": {
                    "type": "NotebookRunnerList",
                    "options": {
                        "spawn_settle_time": 0,
                        "execution_idle_time": 0,
                        "repo_url": str(repo_path),
                        "repo_ref": "main",
                        "collection_rules": [
                            {
                                "type": "include",
                                "patterns": [
                                    "test-notebook-has-services.ipynb",
                                    # This shouldn't run because services
                                    # specified in the in-repo config file are
                                    # missing, which takes precedence
                                    "test-notebook-missing-service.ipynb",
                                    # This shouldn't run because the dir is
                                    # excluded in the in-repo-config file,
                                    # which takes precedence
                                    "some-dir/test-other-notebook-has-services.ipynb",
                                ],
                            }
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
                "name": "NotebookRunnerList",
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
