"""Tests for CiManager."""

import asyncio

import pytest
import structlog
from httpx import AsyncClient
from pydantic import HttpUrl
from pytest_mock import MockerFixture
from rubin.gafaelfawr import GafaelfawrClient

from mobu.dependencies.config import config_dependency
from mobu.events import Events
from mobu.models.ci_manager import (
    CiJobSummary,
    CiManagerSummary,
    CiWorkerSummary,
)
from mobu.models.user import User
from mobu.services.business.base import Business
from mobu.services.github_ci.ci_manager import CiManager
from mobu.services.repo import RepoManager
from mobu.storage.gafaelfawr import GafaelfawrStorage
from tests.support.constants import TEST_GITHUB_CI_APP_PRIVATE_KEY

from ..support.github import GitHubMocker, MockJob


def create_ci_manager(events: Events) -> CiManager:
    """Create a CiManger with appropriately mocked dependencies."""
    config = config_dependency.config
    scopes = [
        "exec:notebook",
        "exec:portal",
        "read:image",
        "read:tap",
    ]

    client = GafaelfawrClient()
    logger = structlog.get_logger()
    gafaelfawr = GafaelfawrStorage(config, client, logger)
    repo_manager = RepoManager(logger=logger)

    return CiManager(
        http_client=AsyncClient(),
        gafaelfawr_storage=gafaelfawr,
        events=events,
        repo_manager=repo_manager,
        logger=logger,
        scopes=scopes,
        github_app_id=123,
        github_private_key=TEST_GITHUB_CI_APP_PRIVATE_KEY,
        users=[
            User(username="bot-mobu-user1"),
            User(username="bot-mobu-user2"),
        ],
    )


async def setup_and_run_jobs(
    jobs: list[MockJob],
    github_mocker: GitHubMocker,
    mocker: MockerFixture,
    events: Events,
) -> None:
    """Create a CiManager, enqueue all jobs, wait for them all to be processed,
    wait for the manager to shut down.
    """
    mocker.patch.object(
        Business, "run_once", new=github_mocker.get_mock_run_function()
    )

    ci_manager = create_ci_manager(events)
    await ci_manager.start()
    aioevents: list[asyncio.Event] = []
    for job in jobs:
        lifecycle = await ci_manager.enqueue(
            installation_id=job.installation_id,
            repo_owner=job.repo_owner,
            repo_name=job.repo_name,
            ref=job.ref,
            pull_number=job.pull_number,
        )
        aioevents.append(lifecycle.processed)
    await asyncio.gather(*[event.wait() for event in aioevents])
    await ci_manager.aclose()


@pytest.mark.asyncio
@pytest.mark.usefixtures("_enable_github_ci_app")
async def test_stops_on_empty_queue(events: Events) -> None:
    ci_manager = create_ci_manager(events)
    await ci_manager.start()
    expected_summary = CiManagerSummary(
        workers=[
            CiWorkerSummary(
                user=User(
                    username="bot-mobu-user1", uidnumber=None, gidnumber=None
                ),
                num_processed=0,
                current_job=None,
            ),
            CiWorkerSummary(
                user=User(
                    username="bot-mobu-user2", uidnumber=None, gidnumber=None
                ),
                num_processed=0,
                current_job=None,
            ),
        ],
        num_queued=0,
    )
    assert ci_manager.summarize() == expected_summary
    await asyncio.wait_for(ci_manager.aclose(), timeout=0.5)


@pytest.mark.asyncio
@pytest.mark.usefixtures("_enable_github_ci_app")
async def test_no_changed_files(
    github_mocker: GitHubMocker,
    mocker: MockerFixture,
    events: Events,
) -> None:
    jobs = [
        github_mocker.job_no_changed_files(id="ref1"),
    ]

    await setup_and_run_jobs(
        jobs=jobs,
        github_mocker=github_mocker,
        mocker=mocker,
        events=events,
    )


@pytest.mark.asyncio
@pytest.mark.usefixtures("_enable_github_ci_app")
async def test_runs_jobs(
    github_mocker: GitHubMocker,
    mocker: MockerFixture,
    events: Events,
) -> None:
    jobs = [
        github_mocker.job_processed_completely(id="ref1", should_fail=False),
        github_mocker.job_processed_completely(id="ref2", should_fail=False),
        github_mocker.job_processed_completely(id="ref3", should_fail=True),
        github_mocker.job_processed_completely(id="ref4", should_fail=True),
    ]

    mocker.patch.object(
        Business, "run_once", new=github_mocker.get_mock_run_function()
    )

    await setup_and_run_jobs(
        jobs=jobs,
        github_mocker=github_mocker,
        mocker=mocker,
        events=events,
    )


@pytest.mark.asyncio
@pytest.mark.usefixtures("_enable_github_ci_app")
async def test_shutdown(
    github_mocker: GitHubMocker, mocker: MockerFixture, events: Events
) -> None:
    """Test that all queued jobs conclude in GitHub during shutdown."""
    completed_jobs = [
        github_mocker.job_processed_completely(
            id="complete_1", should_fail=True
        ),
        github_mocker.job_processed_completely(
            id="complete_2", should_fail=False
        ),
    ]
    in_progress_jobs = [
        github_mocker.job_processed_while_shutting_down(
            id="in_progress_1", should_fail=True
        ),
        github_mocker.job_processed_while_shutting_down(
            id="in_progress_2", should_fail=False
        ),
    ]
    queued_jobs = [
        github_mocker.job_queued_while_shutting_down(id="queued_1"),
        github_mocker.job_queued_while_shutting_down(id="queued_2"),
    ]

    mocker.patch.object(
        Business,
        "run_once",
        new=github_mocker.get_mock_run_function(blocking_jobs=True),
    )

    ci_manager = create_ci_manager(events)
    await ci_manager.start()

    completed_lifecycles = [
        await ci_manager.enqueue(
            installation_id=job.installation_id,
            repo_owner=job.repo_owner,
            repo_name=job.repo_name,
            ref=job.ref,
            pull_number=job.pull_number,
        )
        for job in completed_jobs
    ]

    in_progress_lifecycles = [
        await ci_manager.enqueue(
            installation_id=job.installation_id,
            repo_owner=job.repo_owner,
            repo_name=job.repo_name,
            ref=job.ref,
            pull_number=job.pull_number,
        )
        for job in in_progress_jobs
    ]

    queued_lifecycles = [
        await ci_manager.enqueue(
            installation_id=job.installation_id,
            repo_owner=job.repo_owner,
            repo_name=job.repo_name,
            ref=job.ref,
            pull_number=job.pull_number,
        )
        for job in queued_jobs
    ]

    # Wait for the first two jobs to start processing
    await asyncio.gather(
        *[lifecycle.processing.wait() for lifecycle in completed_lifecycles]
    )

    # Wait for the first two jobs to complete
    for job in completed_jobs:
        job.proceed_event.set()
    await asyncio.gather(
        *[lifecycle.processed.wait() for lifecycle in completed_lifecycles]
    )

    # Wait for the next two jobs to start processing
    await asyncio.gather(
        *[lifecycle.processing.wait() for lifecycle in in_progress_lifecycles]
    )

    # We'll check this later
    summary = ci_manager.summarize()

    # Tell the CI manager to stop and let the next two jobs proceed only when
    # we know the shutdown process has reached a certain point
    task = asyncio.create_task(ci_manager.aclose())
    await ci_manager.lifecycle.marked_remaining.wait()

    for job in in_progress_jobs:
        job.proceed_event.set()
    await task

    # Make sure the jobs that began processing finished processing
    assert all(
        lifecycle.processed.is_set() for lifecycle in in_progress_lifecycles
    )

    # Make sure the queued jobs never procsesed
    assert not any(
        lifecycle.processed.is_set() for lifecycle in queued_lifecycles
    )
    assert not any(
        lifecycle.processing.is_set() for lifecycle in queued_lifecycles
    )

    # Check the point-in-time summary. It's possible for either worker to
    # have either in_progress job.
    expected_summary1 = CiManagerSummary(
        workers=[
            CiWorkerSummary(
                user=User(
                    username="bot-mobu-user1", uidnumber=None, gidnumber=None
                ),
                num_processed=1,
                current_job=CiJobSummary(
                    commit_url=HttpUrl(
                        "https://github.com/repo_owner_in_progress_1/"
                        "repo_name_in_progress_1/commit/ref_in_progress_1"
                    )
                ),
            ),
            CiWorkerSummary(
                user=User(
                    username="bot-mobu-user2", uidnumber=None, gidnumber=None
                ),
                num_processed=1,
                current_job=CiJobSummary(
                    commit_url=HttpUrl(
                        "https://github.com/repo_owner_in_progress_2/"
                        "repo_name_in_progress_2/commit/ref_in_progress_2"
                    )
                ),
            ),
        ],
        num_queued=2,
    )

    expected_summary2 = CiManagerSummary(
        workers=[
            CiWorkerSummary(
                user=User(
                    username="bot-mobu-user1", uidnumber=None, gidnumber=None
                ),
                num_processed=1,
                current_job=CiJobSummary(
                    commit_url=HttpUrl(
                        "https://github.com/repo_owner_in_progress_2/"
                        "repo_name_in_progress_2/commit/ref_in_progress_2"
                    )
                ),
            ),
            CiWorkerSummary(
                user=User(
                    username="bot-mobu-user2", uidnumber=None, gidnumber=None
                ),
                num_processed=1,
                current_job=CiJobSummary(
                    commit_url=HttpUrl(
                        "https://github.com/repo_owner_in_progress_1/"
                        "repo_name_in_progress_1/commit/ref_in_progress_1"
                    )
                ),
            ),
        ],
        num_queued=2,
    )
    assert summary.model_dump(mode="json") in (
        expected_summary1.model_dump(mode="json"),
        expected_summary2.model_dump(mode="json"),
    )
