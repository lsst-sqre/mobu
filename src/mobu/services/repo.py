"""Helpers for cloning and filtering notebook repos."""

import asyncio
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from structlog.stdlib import BoundLogger

from ..models.repo import ClonedRepoInfo
from ..sentry import capturing_start_span
from ..storage.git import Git

__all__ = ["RepoManager"]


@dataclass(frozen=True)
class _Key:
    """Information to hash a repo clone."""

    url: str
    ref: str


@dataclass(frozen=True)
class _Reference:
    """Information to hash a repo clone."""

    url: str
    ref: str
    hash: str


@dataclass
class _ReferenceCount:
    """A count and a directory to remove when the count reaches 0."""

    count: int
    dir: TemporaryDirectory


class RepoManager:
    """A reference-counting caching repo cloner.

    Only the first call to ``clone`` for a given repo url and ref will clone
    the repo. Subsequent calls will return the location and hash of the
    already-cloned repo.

    A call to ``invalidate`` will make it so that the next call to ``clone``
    will re-clone the repo to a different path.

    A call to ``clone`` also increases a reference counter for the url + ref +
    hash combo of the cloned repo. A call to ``invalidate`` for that combo
    decreases the counter. ``Invalidate`` will only delete the files from the
    cloned repo if the reference count drops to 0.

    Parameters
    ----------
    logger
        A logger
    """

    def __init__(self, logger: BoundLogger, *, testing: bool = False) -> None:
        self._dir = TemporaryDirectory(delete=False, prefix="mobu-notebooks-")
        self._cache: dict[_Key, ClonedRepoInfo] = {}
        self._lock = asyncio.Lock()
        self._logger = logger
        self._references: dict[_Reference, _ReferenceCount] = {}
        self._testing = testing

        # This is just for testing
        self._cloned: list[_Key] = []

    async def clone(self, url: str, ref: str) -> ClonedRepoInfo:
        """Clone a git repo or return cached info by url + ref.

        Increase the reference count for the url + ref + hash combo.

        Parameters
        ----------
        url
            The URL of the repo to clone
        ref
            The git ref to checkout after the repo is cloned
        """
        logger = self._logger.bind(url=url, ref=ref)
        key = _Key(url=url, ref=ref)

        async with self._lock:
            # If the notebook repo has already been cloned, return the info
            if info := self._cache.get(key):
                logger.info("Notebook repo cached")
                reference = _Reference(url=url, ref=ref, hash=info.hash)
                count = self._references[reference]
                count.count += 1
                return info

            # If not, clone the repo
            logger.info("Cloning notebook repo")
            repo_dir = TemporaryDirectory(delete=False, dir=self._dir.name)
            with capturing_start_span(op="clone_repo"):
                git = Git(logger=self._logger)
                git.repo = Path(repo_dir.name)
                await git.clone(url, repo_dir.name)
                await git.checkout(ref)
                repo_hash = await git.repo_hash()

            # If we're in testing mode, record that we actually did a clone
            if self._testing:
                self._cloned.append(key)

            info = ClonedRepoInfo(
                dir=repo_dir, path=Path(repo_dir.name), hash=repo_hash
            )

            # Update the cache with the cloned repo's info
            self._cache[key] = info

            # Update the reference count
            reference = _Reference(url=url, ref=ref, hash=info.hash)
            self._references[reference] = _ReferenceCount(
                count=1, dir=info.dir
            )
            return info

    async def invalidate(self, url: str, ref: str, repo_hash: str) -> None:
        """Invalidate a git repo in the cache by url + ref.

        Decrease the url + ref + hash reference count. If it drops to zero,
        delete the files from that clone.

        Parameters
        ----------
        url
            The URL of the repo to clone
        ref
            The git ref to checkout after the repo is cloned
        hash
            The hash of the cloned repo to remove
        """
        logger = self._logger.bind(url=url, ref=ref, hash=repo_hash)
        key = _Key(url=url, ref=ref)
        reference = _Reference(url=url, ref=ref, hash=repo_hash)

        # This theoretically doesn't need a lock, but if we add any awaits here
        # in the future, we'd need to add a lock, and it would be pretty easy
        # to forget to do it.
        async with self._lock:
            info = self._cache.get(key)
            if info:
                logger.info("Invalidating repo")

                # Note that this could force an unnecessary clone if any monkey
                # is calling invalidate in its shutdown method. This would
                # force reclone for other monkeys that are using the same repo
                # at the same hash.
                del self._cache[key]

            count = self._references.get(reference)
            if count:
                count.count -= 1
                if count.count == 0:
                    logger.info(f"0 references, deleting: {count.dir.name}")
                    count.dir.cleanup()
                    del self._references[reference]

    def close(self) -> None:
        """Delete all cloned repos and containing directory."""
        self._dir.cleanup()
