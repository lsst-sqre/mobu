"""Tests for Monkeyflocker"""

import json

from jinja2 import BaseLoader, Environment

from monkeyflocker.client import MonkeyflockerClient

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
