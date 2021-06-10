"""monkeyflocker dispatches or destroys a troop of mobu instances.  This is
its CLI.
"""

import asyncio
from typing import Optional

import click
import jinja2

from .client import MonkeyflockerClient as MFClient
from .error import MonkeyflockerError as MFError

MF_PREFIX = "MONKEYFLOCKER_"

# Set up our UI


@click.command()
@click.argument("verb")
@click.option(
    "-n",
    "--count",
    envvar=f"{MF_PREFIX}COUNT",
    type=int,
    default=5,
    help="Number of mobu workers to run.",
)
@click.option(
    "-e",
    "--base-url",
    "--base-url-endpoint",
    envvar=f"{MF_PREFIX}BASE_URL",
    default="http://localhost:8000",
    help="URL of RSP instance to dispatch mobu workers on",
)
@click.option(
    "-l",
    "--base-username",
    default="lsptestuser",
    envvar=f"{MF_PREFIX}BASE_USERNAME",
    help="Base user name (without sequence number) for mobu workers",
)
@click.option(
    "-u",
    "--base-uid",
    type=int,
    default=60180,
    envvar=f"{MF_PREFIX}BASE_UID",
    help="Base UID (0-indexed) for mobu workers",
)
@click.option(
    "-t",
    "--template-file",
    "--user-template-file",
    default="./user-template.json",
    envvar=f"{MF_PREFIX}USER_TEMPLATE",
    help="User template JSON file for mobu workers",
)
@click.option(
    "-k",
    "--token",
    "--access-token",
    envvar=["ACCESS_TOKEN", f"{MF_PREFIX}ACCESS_TOKEN"],
    help="Token to use to drive mobu",
)
def main(
    verb: str,
    count: int,
    base_url: str,
    base_username: str,
    base_uid: int,
    token: Optional[str],
    template_file: str,
) -> None:
    verb = verb.lower()
    # Validate our parameters
    if verb not in ["start", "stop"]:
        raise MFError("Verb must be 'start' or 'stop'")
    if count < 1:
        raise MFError("Count must be a positive integer")
    if base_uid < 0:
        raise MFError("Base_UID must be a non-negative integer")
    if not token:
        raise MFError("Access token must be set")
    te = jinja2.Environment(loader=jinja2.FileSystemLoader(searchpath="./"))
    template = te.get_template(template_file)
    endpoint = f"{base_url}/mobu/user"
    client = MFClient(
        count, base_username, base_uid, endpoint, token, template
    )
    asyncio.run(client.execute(verb))
