"""Functions and constants for mocking out GitHub API behavior."""

import asyncio
from collections.abc import Callable

import respx

from mobu.services.business.base import Business
from mobu.services.github_ci.ci_manager import CiManager

__all__ = ["GitHubMocker", "MockJob"]


class MockJob:
    """State and config for some fake work to be done by CiManager in tests."""

    def __init__(self, id: str, *, should_fail: bool = False) -> None:
        self.id = id
        self.installation_id = 123
        self.should_fail = should_fail
        self.proceed_event = asyncio.Event()
        self.path_prefix = f"/repos/{self.repo_owner}/{self.repo_name}"

    @property
    def repo_owner(self) -> str:
        return f"repo_owner_{self.id}"

    @property
    def repo_name(self) -> str:
        return f"repo_name_{self.id}"

    @property
    def ref(self) -> str:
        return f"ref_{self.id}"


class GitHubMocker:
    """A big bucket of mocks and state to mock GitHub API behavior.

    Create an instance of this class and then call functions to mock GitHub API
    responses and job functionality based on desired behavior.
    This is very stateful, and asserts that an exact set of HTTP calls are
    made--no more, and no less.
    The general pattern:
      1. Call a bunch of job_* methods to mock behavior for those usecases
      2. Hang on to the ``MockJob``s returned from those calls
      3. Patch ``Business.run_once`` with ``get_mock_run_function``
      4. Start a CiManager, and ``enqueue`` jobs with the info from the MockJob
         values
      5. Do whatever you need to do to cause the situations :)
         This may include waiting and triggering various ``asyncio.Event``s
    """

    def __init__(self) -> None:
        self._blocking_jobs = False
        self.jobs: list[MockJob] = []

        self.router = respx.mock(
            base_url="https://api.github.com",
            assert_all_mocked=True,
            assert_all_called=True,
        )

        # Mock the endpoint that gives us a token
        self.router.post(
            url__regex=r"/app/installations/(?P<installation_id>\d+)/access_tokens",
        ).respond(
            json={
                "token": "whatever",
                "expires_at": "whenever",
            }
        )

    def job_no_changed_files(self, id: str) -> MockJob:
        """Causes an GitHub API response indicating no notebooks have
        changed.
        """
        job = MockJob(id=id)
        self.jobs.append(job)

        self._mock_get_changed_files(job, has_changed_files=False)

        # Create a check run with a `queued` status
        self.router.post(
            path=f"{job.path_prefix}/check-runs",
        ).respond(json={"id": "1"})

        # The check never starts because there are no changed files

        # The check always succeeds
        self.router.patch(
            path=f"{job.path_prefix}/check-runs/1",
            json__conclusion="success",
        )

        return job

    def job_processed_completely(
        self, id: str, *, should_fail: bool
    ) -> MockJob:
        """Mock the GitHub API for a job that processes completely with
        no interruption.
        """
        job = MockJob(id=id, should_fail=should_fail)
        self.jobs.append(job)

        self._mock_get_changed_files(job)

        # Create a check run with a `queued` status
        self.router.post(
            path=f"{job.path_prefix}/check-runs",
        ).respond(json={"id": "1"})

        # Eventually mark the check run 'in progress'
        self.router.patch(
            path=f"{job.path_prefix}/check-runs/1", json__status="in_progress"
        )

        # Mark the check run failed or succeeded
        conclusion = "failure" if job.should_fail else "success"
        self.router.patch(
            path=f"{job.path_prefix}/check-runs/1",
            json__conclusion=conclusion,
        )

        return job

    def job_processed_while_shutting_down(
        self, id: str, *, should_fail: bool
    ) -> MockJob:
        """Mock the GitHub API for a job that processes completely, but is
        in-progress when mobu shuts down.
        """
        job = MockJob(id=id, should_fail=should_fail)
        self.jobs.append(job)

        self._mock_get_changed_files(job)

        # Create a check run with a `queued` status
        self.router.post(
            path=f"{job.path_prefix}/check-runs",
        ).respond(json={"id": "1"})

        # Eventually mark the check run 'in progress'
        self.router.patch(
            path=f"{job.path_prefix}/check-runs/1", json__status="in_progress"
        )

        # The check will be marked as failed due to Mobu shutdown...
        self.router.patch(
            path=f"{job.path_prefix}/check-runs/1",
            json__conclusion="failure",
            json__output__text=CiManager.shutdown_error_msg,
        )

        # But it should eventually complete
        conclusion = "failure" if job.should_fail else "success"
        self.router.patch(
            path=f"{job.path_prefix}/check-runs/1",
            json__conclusion=conclusion,
        )

        return job

    def job_queued_while_shutting_down(self, id: str) -> MockJob:
        """Mock the GitHub API for a job that gets queued, but never
        processed.
        """
        job = MockJob(id=id)
        self.jobs.append(job)

        # Create a check run with a `queued` status
        self.router.post(
            path=f"{job.path_prefix}/check-runs",
        ).respond(json={"id": "1"})

        # The check should never be marked as in progress

        # The check should never be updated based on compleion of the job

        # The check will be marked as failed due to Mobu shutdown
        self.router.patch(
            path=f"{job.path_prefix}/check-runs/1",
            json__conclusion="failure",
            json__output__text=CiManager.shutdown_error_msg,
        )

        return job

    def enable_blocking_jobs(self) -> None:
        """Make it so that you must set an asyncio.Event in your test for the
        job to progress.
        """
        self._blocking_jobs = True

    def get_mock_run_function(
        self, *, blocking_jobs: bool = False
    ) -> Callable:
        """Patch this in to mobu.services.buiness.base.Business.run_once.

        It will:
          * Raise an exception while trying to run any job that was
            configured to fail
          * Optionally require an asyncio.Event to be set in order to progress
        """

        async def run_once(host_self: Business) -> None:
            ref = host_self.options.repo_ref
            job = next(job for job in self.jobs if job.ref == ref)
            if blocking_jobs:
                await job.proceed_event.wait()
            if job.should_fail:
                raise RuntimeError("Blowing up on purpose!")

        return run_once

    def _mock_get_changed_files(
        self, job: MockJob, *, has_changed_files: bool = True
    ) -> None:
        """Mock different responses from the commits API."""
        if has_changed_files:
            changes = [
                {"filename": "notebook_changed1.ipynb", "status": "modified"},
                {"filename": "notebook_deleted.ipynb", "status": "removed"},
                {"filename": "not_a_notebook.txt", "status": "modified"},
                {"filename": "notebook_changed2.ipynb", "status": "modified"},
            ]
        else:
            changes = [
                {"filename": "notebook_deleted.ipynb", "status": "removed"},
            ]

        self.router.get(path=f"{job.path_prefix}/commits/{job.ref}").respond(
            json={"files": changes}
        )
