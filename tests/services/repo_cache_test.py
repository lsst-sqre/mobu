"""Tests for the RepoCache."""

import shutil
from asyncio import gather
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from mobu.services.repo import RepoManager
from mobu.storage.git import Git
from tests.support.util import setup_git_repo

from ..support.constants import TEST_DATA_DIR


@pytest.mark.asyncio
async def test_cache(
    tmp_path: Path,
) -> None:
    # Set up a notebook repository.
    source_path = TEST_DATA_DIR / "notebooks"
    repo_path = tmp_path / "notebooks"
    repo_ref = "main"

    shutil.copytree(str(source_path), str(repo_path))
    await setup_git_repo(repo_path)

    mock_logger = MagicMock()
    manager = RepoManager(logger=mock_logger, testing=True)

    # Clone the same repo and ref a bunch of times concurrently
    clone_tasks = [
        manager.clone(url=str(repo_path), ref=repo_ref) for _ in range(100)
    ]
    infos = await gather(*clone_tasks)

    # The same info should be returned for every call
    assert len(set(infos)) == 1
    original_info = infos[0]

    # The repo should have been cloned
    contents = (original_info.path / "test-notebook.ipynb").read_text()
    assert "This is a test" in contents
    assert "This is a NEW test" not in contents

    # ...once
    assert len(manager._cloned) == 1
    manager._cloned = []

    # Change the notebook and git commit it
    notebook = repo_path / "test-notebook.ipynb"
    contents = notebook.read_text()
    new_contents = contents.replace("This is a test", "This is a NEW test")
    notebook.write_text(new_contents)

    git = Git(repo=repo_path)
    await git.add(str(notebook))
    await git.commit("-m", "Updating notebook")

    # The repo should be cached (this makes the reference count 101)
    cached_info = await manager.clone(url=str(repo_path), ref=repo_ref)
    assert cached_info == original_info
    contents = (cached_info.path / "test-notebook.ipynb").read_text()
    assert "This is a test" in contents
    assert "This is a NEW test" not in contents

    # Invalidate this URL and ref. This should make the next clone call clone
    # the repo again, but it should not delete the directory of the old
    # checkout because there are still 100 references to it.
    await manager.invalidate(
        url=str(repo_path), ref=repo_ref, repo_hash=original_info.hash
    )

    # Clone it again and verify stuff
    clone_tasks = [
        manager.clone(url=str(repo_path), ref=repo_ref) for _ in range(100)
    ]
    infos = await gather(*clone_tasks)
    assert len(set(infos)) == 1
    assert len(manager._cloned) == 1
    updated_info = infos[0]

    # We should get different info because the repo should have been recloned
    assert updated_info != original_info

    # The repo should be updated
    contents = (updated_info.path / "test-notebook.ipynb").read_text()
    assert "This is a test" not in contents
    assert "This is a NEW test" in contents

    # The original dir should NOT be deleted
    assert Path(original_info.dir.name).exists()

    # invalidate the other references
    remove_tasks = [
        manager.invalidate(
            url=str(repo_path), ref=repo_ref, repo_hash=original_info.hash
        )
        for _ in range(100)
    ]
    await gather(*remove_tasks)

    # The original dir should be deleted
    assert not Path(original_info.dir.name).exists()

    # The cache should clean up after itself
    manager.close()
    assert not original_info.path.exists()
    assert not updated_info.path.exists()
