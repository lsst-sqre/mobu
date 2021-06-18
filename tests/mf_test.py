"""Tests for Monkeyflocker"""

import json
import os

from click.testing import CliRunner, Result
from jinja2 import BaseLoader, Environment

from monkeyflocker.cli import main as MF
from monkeyflocker.client import MonkeyflockerClient
from monkeyflocker.error import MonkeyflockerError

TEMPLATE = """
{
  "name": "{{USERNAME}}",
  "user": {
    "username": "{{USERNAME}}",
    "uidnumber": {{UID}},
    "scopes": ["exec:notebook"]
  },
  "business": "JupyterLoginLoop",
  "options": {
    "restart": true
  }
}
"""


async def test_client_creation() -> None:
    """Test client fields get filled in correctly."""
    client = MonkeyflockerClient(
        count=2,
        base_username="mobutest",
        base_uid=29029,
        endpoint="https://madeup.fake.name",
        token="dummy-token",
        output="",
        template=Environment(loader=BaseLoader()).from_string(TEMPLATE),
    )
    userlist = client.users
    assert userlist[0].name == "mobutest01"
    assert userlist[0].uid == 29030
    assert userlist[1].name == "mobutest02"
    assert userlist[1].uid == 29031
    rendered_json = client.template.render(
        USERNAME=userlist[0].name, UID=userlist[0].uid
    )
    rendered_obj = json.loads(rendered_json)
    assert rendered_obj["name"] == userlist[0].name
    assert rendered_obj["user"]["uidnumber"] == userlist[0].uid


def test_mf_errors() -> None:
    runner = CliRunner()
    # No verb
    result = runner.invoke(MF)
    assert result.exit_code == 2
    # Unknown option
    result = runner.invoke(MF, ["stop", "--florp"])
    assert result.exit_code == 2
    # Template file not found
    result = runner.invoke(
        MF,
        [
            "stop",
            "--token",
            "--dummy-token",
            "--template",
            "/this/path/does/not/exist",
        ],
    )
    assert result.exit_code == 2
    # Bad count (float, caught by click)
    result = runner.invoke(MF, ["stop", "--count", "1.2"])
    assert result.exit_code == 2
    # Bad count (negative)
    result = runner.invoke(MF, ["stop", "--count", "-2"])
    _check_mf_error(result, "Count must be a positive integer")
    # Bad count (zero)
    result = runner.invoke(MF, ["stop", "--count", "0"])
    _check_mf_error(result, "Count must be a positive integer")
    # Bad UID (float, caught by click)
    result = runner.invoke(MF, ["stop", "--base-uid", "1.2"])
    assert result.exit_code == 2
    # Bad UID (negative)
    result = runner.invoke(MF, ["stop", "--base-uid", "-2"])
    _check_mf_error(result, "Base_UID must be a non-negative integer")
    # Make sure there's no access token
    os.environ["ACCESS_TOKEN"] = ""
    os.environ["MF_ACCESS_TOKEN"] = ""
    # No access token
    result = runner.invoke(MF, ["stop"])
    _check_mf_error(result, "Access token must be set")


def _check_mf_error(result: Result, err: str) -> None:
    assert result.exit_code == 1
    exc = result.exception
    assert type(exc) is MonkeyflockerError
    assert str(exc) == err
