"""Tests for the NotebookFinder service."""

import shutil
from pathlib import Path

from structlog.stdlib import get_logger

from mobu.models.repo import RepoConfig
from mobu.services.notebook_finder import NotebookFinder

from ..support.constants import TEST_DATA_DIR


def _get_repo_path(
    tmp_path: Path, subpath: str = "notebooks_recursive"
) -> Path:
    """Copy test repo files into a tmp path."""
    source_path = TEST_DATA_DIR / subpath
    repo_path = tmp_path / "notebooks"
    shutil.copytree(str(source_path), str(repo_path))
    return repo_path


def _normalize(root: Path, paths: set[Path]) -> set[str]:
    """Normalize results for comparison."""
    stripped = {path.relative_to(root) for path in paths}
    return {str(path) for path in stripped}


def test_default(tmp_path: Path) -> None:
    repo_path = _get_repo_path(tmp_path)
    finder = NotebookFinder(
        repo_path=repo_path,
        repo_config=RepoConfig(),
        available_services={"some_service"},
        logger=get_logger(__file__),
    )
    found = _normalize(repo_path, finder.find())
    expected = {
        "exception.ipynb",
        "some-other-dir/nested-dir/double-nested-dir/test-double-nested-dir.ipynb",
        "some-dir/test-some-dir-notebook.ipynb",
        "some-other-dir/test-some-other-dir.ipynb",
        "test-notebook.ipynb",
    }

    assert found == expected


def test_exclude_dirs(tmp_path: Path) -> None:
    repo_path = _get_repo_path(tmp_path)
    finder = NotebookFinder(
        repo_path=repo_path,
        repo_config=RepoConfig(),
        available_services={"some_service"},
        exclude_dirs={Path("some-other-dir/nested-dir/")},
        logger=get_logger(__file__),
    )
    found = _normalize(repo_path, finder.find())
    expected = {
        "exception.ipynb",
        "some-dir/test-some-dir-notebook.ipynb",
        "some-other-dir/test-some-other-dir.ipynb",
        "test-notebook.ipynb",
    }

    assert found == expected

    finder = NotebookFinder(
        repo_path=repo_path,
        repo_config=RepoConfig(),
        available_services={"some_service"},
        exclude_dirs={Path("some-other-dir/nested-dir/"), Path("some-dir")},
        logger=get_logger(__file__),
    )
    found = _normalize(repo_path, finder.find())
    expected = {
        "exception.ipynb",
        "some-other-dir/test-some-other-dir.ipynb",
        "test-notebook.ipynb",
    }

    assert found == expected


def test_exlclude_dirs_override(tmp_path: Path) -> None:
    repo_path = _get_repo_path(tmp_path)
    finder = NotebookFinder(
        repo_path=repo_path,
        repo_config=RepoConfig(
            exclude_dirs={Path("some-other-dir/nested-dir/")}
        ),
        available_services={"some_service"},
        exclude_dirs={Path("some-other-dir/nested-dir/"), Path("some-dir")},
        logger=get_logger(__file__),
    )
    found = _normalize(repo_path, finder.find())
    expected = {
        "exception.ipynb",
        "some-dir/test-some-dir-notebook.ipynb",
        "some-other-dir/test-some-other-dir.ipynb",
        "test-notebook.ipynb",
    }

    assert found == expected


def test_exclude_patterns(tmp_path: Path) -> None:
    repo_path = _get_repo_path(tmp_path)
    finder = NotebookFinder(
        repo_path=repo_path,
        repo_config=RepoConfig(),
        available_services={"some_service"},
        exclude_patterns={"**/nested-dir/**"},
        logger=get_logger(__file__),
    )
    found = _normalize(repo_path, finder.find())
    expected = {
        "exception.ipynb",
        "some-dir/test-some-dir-notebook.ipynb",
        "some-other-dir/test-some-other-dir.ipynb",
        "test-notebook.ipynb",
    }

    assert found == expected

    finder = NotebookFinder(
        repo_path=repo_path,
        repo_config=RepoConfig(),
        available_services={"some_service"},
        exclude_patterns={"**/nested-dir/**", "**/test-some-other-dir*"},
        logger=get_logger(__file__),
    )
    found = _normalize(repo_path, finder.find())
    expected = {
        "exception.ipynb",
        "some-dir/test-some-dir-notebook.ipynb",
        "test-notebook.ipynb",
    }

    assert found == expected


def test_exclude_patterns_override(tmp_path: Path) -> None:
    repo_path = _get_repo_path(tmp_path)
    finder = NotebookFinder(
        repo_path=repo_path,
        repo_config=RepoConfig(
            exclude_patterns={"**/nested-dir/**"},
        ),
        available_services={"some_service"},
        exclude_patterns={"**"},
        logger=get_logger(__file__),
    )
    found = _normalize(repo_path, finder.find())
    expected = {
        "exception.ipynb",
        "some-dir/test-some-dir-notebook.ipynb",
        "some-other-dir/test-some-other-dir.ipynb",
        "test-notebook.ipynb",
    }
    assert found == expected


def test_include_patterns(tmp_path: Path) -> None:
    repo_path = _get_repo_path(tmp_path)
    finder = NotebookFinder(
        repo_path=repo_path,
        repo_config=RepoConfig(),
        available_services={"some_service"},
        include_patterns={"**/nested-dir/**", "some-dir/**"},
        logger=get_logger(__file__),
    )
    found = _normalize(repo_path, finder.find())
    expected = {
        "some-dir/test-some-dir-notebook.ipynb",
        "some-other-dir/nested-dir/double-nested-dir/test-double-nested-dir.ipynb",
    }

    assert found == expected


def test_include_patterns_override(tmp_path: Path) -> None:
    repo_path = _get_repo_path(tmp_path)
    finder = NotebookFinder(
        repo_path=repo_path,
        repo_config=RepoConfig(include_patterns={"exception.ipynb"}),
        available_services={"some_service"},
        include_patterns={"nope"},
        logger=get_logger(__file__),
    )
    found = _normalize(repo_path, finder.find())
    expected = {"exception.ipynb"}

    assert found == expected


def test_only_patterns(tmp_path: Path) -> None:
    repo_path = _get_repo_path(tmp_path)
    finder = NotebookFinder(
        repo_path=repo_path,
        repo_config=RepoConfig(),
        available_services={"some_service"},
        only_patterns={"some-other-dir/**", "**/test-double-*"},
        logger=get_logger(__file__),
    )
    found = _normalize(repo_path, finder.find())
    expected = {
        "some-other-dir/nested-dir/double-nested-dir/test-double-nested-dir.ipynb",
    }

    assert found == expected


def test_only_patterns_override(tmp_path: Path) -> None:
    repo_path = _get_repo_path(tmp_path)
    finder = NotebookFinder(
        repo_path=repo_path,
        repo_config=RepoConfig(
            only_patterns={"some-other-dir/**", "**/test-double-*"},
        ),
        available_services={"some_service"},
        only_patterns={"nope"},
        logger=get_logger(__file__),
    )
    found = _normalize(repo_path, finder.find())
    expected = {
        "some-other-dir/nested-dir/double-nested-dir/test-double-nested-dir.ipynb",
    }

    assert found == expected


def test_excludes_available_services(tmp_path: Path) -> None:
    repo_path = _get_repo_path(tmp_path, "notebooks_services")
    finder = NotebookFinder(
        repo_path=repo_path,
        repo_config=RepoConfig(),
        available_services={"some_service"},
        logger=get_logger(__file__),
    )
    found = _normalize(repo_path, finder.find())
    expected = {
        "some-dir/test-other-notebook-has-services.ipynb",
        "test-notebook-has-services.ipynb",
    }

    assert found == expected
