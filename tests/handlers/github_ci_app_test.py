"""Test the github ci app webhook handler."""

import hashlib
import hmac
from dataclasses import dataclass
from string import Template

import pytest
import respx
from httpx import AsyncClient
from pytest_mock import MockerFixture

from mobu.services.github_ci.ci_manager import CiManager

from ..support.constants import TEST_DATA_DIR, TEST_GITHUB_CI_APP_SECRET
from ..support.gafaelfawr import mock_gafaelfawr


@dataclass
class GitHubRequest:
    payload: str
    headers: dict[str, str]


def webhook_request(
    *,
    event: str,
    action: str,
    owner: str = "org1",
    repo: str = "repo1",
    sha: str = "abc123",
) -> GitHubRequest:
    """Build a GitHub webhook request and headers with the right hash."""
    data_path = TEST_DATA_DIR / "github_webhooks"
    template = (data_path / f"{event}_{action}.tmpl.json").read_text()
    payload = Template(template).substitute(
        owner=owner,
        repo=repo,
        sha=sha,
        installation_id=123,
    )

    # https://docs.github.com/en/webhooks/using-webhooks/validating-webhook-deliveries#python-example
    hash_object = hmac.new(
        TEST_GITHUB_CI_APP_SECRET.encode(),
        msg=payload.encode(),
        digestmod=hashlib.sha256,
    )
    sig = "sha256=" + hash_object.hexdigest()

    headers = {
        "Accept": "*/*",
        "Content-Type": "application/json",
        "User-Agent": "GitHub-Hookshot/c9d6c0a",
        "X-GitHub-Delivery": "d2d3c948-1d61-11ef-848a-c578f23615c9",
        "X-GitHub-Event": event,
        "X-GitHub-Hook-ID": "479971864",
        "X-GitHub-Hook-Installation-Target-ID": "1",
        "X-GitHub-Hook-Installation-Target-Type": "integration",
        "X-Hub-Signature-256": sig,
    }

    return GitHubRequest(payload=payload, headers=headers)


@pytest.mark.asyncio
async def test_not_enabled(
    anon_client: AsyncClient,
    respx_mock: respx.Router,
) -> None:
    mock_gafaelfawr(respx_mock)
    request = webhook_request(
        event="pull_request",
        action="synchronize",
    )
    response = await anon_client.post(
        "/mobu/github/ci/webhook",
        headers=request.headers,
        content=request.payload,
    )

    assert response.status_code == 404


@pytest.mark.asyncio
@pytest.mark.usefixtures("_enable_github_ci_app")
async def test_unacceptable_org(
    anon_client: AsyncClient,
    respx_mock: respx.Router,
    mocker: MockerFixture,
) -> None:
    mock_gafaelfawr(respx_mock)
    request = webhook_request(
        event="pull_request",
        action="synchronize",
        owner="nope",
    )

    mock_func = mocker.patch.object(
        CiManager,
        "enqueue",
    )
    response = await anon_client.post(
        "/mobu/github/ci/webhook",
        headers=request.headers,
        content=request.payload,
    )

    assert response.status_code == 403
    assert not mock_func.called


@pytest.mark.asyncio
@pytest.mark.usefixtures("_enable_github_ci_app")
@pytest.mark.parametrize(
    "gh_request",
    [
        webhook_request(
            event="pull_request",
            action="synchronize",
        ),
        webhook_request(
            event="pull_request",
            action="opened",
        ),
    ],
)
async def test_should_enqueue(
    anon_client: AsyncClient,
    respx_mock: respx.Router,
    mocker: MockerFixture,
    gh_request: GitHubRequest,
) -> None:
    mock_gafaelfawr(respx_mock)

    mock_func = mocker.patch.object(
        CiManager,
        "enqueue",
    )

    response = await anon_client.post(
        "/mobu/github/ci/webhook",
        headers=gh_request.headers,
        content=gh_request.payload,
    )

    assert response.status_code == 202
    assert mock_func.called
