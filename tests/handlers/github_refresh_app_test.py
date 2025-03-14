"""Test the github refresh webhook handler."""

import hashlib
import hmac
from dataclasses import dataclass
from string import Template

import pytest
import respx
from httpx import AsyncClient
from pytest_mock import MockerFixture

from ..support.constants import TEST_DATA_DIR, TEST_GITHUB_REFRESH_APP_SECRET
from ..support.gafaelfawr import mock_gafaelfawr


@dataclass(frozen=True)
class GithubRequest:
    payload: str
    headers: dict[str, str]


def webhook_request(org: str, repo: str, ref: str) -> GithubRequest:
    """Build a Github webhook request and headers with the right hash."""
    data_path = TEST_DATA_DIR / "github_webhooks"
    template = (data_path / "push.tmpl.json").read_text()
    payload = Template(template).substitute(org=org, repo=repo, ref=ref)

    # https://docs.github.com/en/webhooks/using-webhooks/validating-webhook-deliveries#python-example
    hash_object = hmac.new(
        TEST_GITHUB_REFRESH_APP_SECRET.encode(),
        msg=payload.encode(),
        digestmod=hashlib.sha256,
    )
    sig = "sha256=" + hash_object.hexdigest()

    headers = {
        "Accept": "*/*",
        "Content-Type": "application/json",
        "User-Agent": "GitHub-Hookshot/c9d6c0a",
        "X-GitHub-Delivery": "d2d3c948-1d61-11ef-848a-c578f23615c9",
        "X-GitHub-Event": "push",
        "X-GitHub-Hook-ID": "479971864",
        "X-GitHub-Hook-Installation-Target-ID": "1",
        "X-GitHub-Hook-Installation-Target-Type": "integration",
        "X-Hub-Signature-256": sig,
    }

    return GithubRequest(payload=payload, headers=headers)


@pytest.mark.asyncio
@pytest.mark.usefixtures("_no_monkey_business")
async def test_not_enabled(
    anon_client: AsyncClient,
    respx_mock: respx.Router,
) -> None:
    mock_gafaelfawr(respx_mock)
    request = webhook_request(
        org="lsst-sqre",
        repo="some-repo",
        ref="refs/heads/main",
    )
    response = await anon_client.post(
        "/mobu/github/refresh/webhook",
        headers=request.headers,
        content=request.payload,
    )

    assert response.status_code == 404


@pytest.mark.asyncio
@pytest.mark.usefixtures("_enable_github_refresh_app")
async def test_unacceptable_org(
    anon_client: AsyncClient,
    respx_mock: respx.Router,
    mocker: MockerFixture,
) -> None:
    mock_gafaelfawr(respx_mock)
    request = webhook_request(
        org="nope",
        repo="some-repo",
        ref="refs/heads/main",
    )

    response = await anon_client.post(
        "/mobu/github/refresh/webhook",
        headers=request.headers,
        content=request.payload,
    )

    assert response.status_code == 403


@pytest.mark.asyncio
@pytest.mark.usefixtures("_no_monkey_business", "_enable_github_refresh_app")
async def test_handle_webhook(
    client: AsyncClient,
    anon_client: AsyncClient,
    respx_mock: respx.Router,
) -> None:
    configs = [
        {
            "name": "test-notebook",
            "count": 1,
            "user_spec": {"username_prefix": "bot-mobu-testuser-notebook"},
            "scopes": ["exec:notebook"],
            "business": {
                "type": "NotebookRunnerCounting",
                "options": {
                    "repo_url": "https://github.com/lsst-sqre/some-repo.git",
                    "repo_ref": "main",
                },
            },
        },
        {
            "name": "test-notebook-branch",
            "count": 1,
            "user_spec": {
                "username_prefix": "bot-mobu-testuser-notebook-branch"
            },
            "scopes": ["exec:notebook"],
            "business": {
                "type": "NotebookRunnerCounting",
                "options": {
                    "repo_url": "https://github.com/lsst-sqre/some-repo.git",
                    "repo_ref": "some-branch",
                },
            },
        },
        {
            "name": "test-other-notebook",
            "count": 1,
            "user_spec": {
                "username_prefix": "bot-mobu-testuser-other-notebook"
            },
            "scopes": ["exec:notebook"],
            "business": {
                "type": "NotebookRunnerCounting",
                "options": {
                    "repo_url": "https://github.com/lsst-sqre/some-other-repo.git",
                    "repo_ref": "main",
                },
            },
        },
        {
            "name": "test-non-notebook",
            "count": 1,
            "user_spec": {"username_prefix": "bot-mobu-testuser-non-notebook"},
            "scopes": ["exec:notebook"],
            "business": {"type": "EmptyLoop"},
        },
    ]

    mock_gafaelfawr(respx_mock)

    # Start the flocks
    for config in configs:
        r = await client.put("/mobu/flocks", json=config)
        assert r.status_code == 201

    # Post a webhook event like GitHub would
    request = webhook_request(
        org="lsst-sqre",
        repo="some-repo",
        ref="refs/heads/main",
    )
    response = await anon_client.post(
        "/mobu/github/refresh/webhook",
        headers=request.headers,
        content=request.payload,
    )

    assert response.status_code == 202

    # Only the business for the correct branch and repo should be refreshing
    r = await client.get(
        "/mobu/flocks/test-notebook/monkeys/bot-mobu-testuser-notebook1"
    )
    assert r.json()["business"]["refreshing"] is True

    # The other businesses should not be refreshing
    r = await client.get(
        "/mobu/flocks/test-notebook-branch/monkeys/bot-mobu-testuser-notebook-branch1"
    )
    assert r.json()["business"]["refreshing"] is False

    r = await client.get(
        "/mobu/flocks/test-other-notebook/monkeys/bot-mobu-testuser-other-notebook1"
    )
    assert r.json()["business"]["refreshing"] is False

    r = await client.get(
        "/mobu/flocks/test-non-notebook/monkeys/bot-mobu-testuser-non-notebook1"
    )
    assert r.json()["business"]["refreshing"] is False
