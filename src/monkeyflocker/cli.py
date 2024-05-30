"""Command-line client to manage a flock of monkeys."""

from __future__ import annotations

from pathlib import Path

import click
from safir.asyncio import run_with_asyncio

from .client import MonkeyflockerClient


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(message="%(version)s")
def main() -> None:
    """Command-line interface to manage mobu monkeys."""


@main.command()
@click.argument("topic", default=None, required=False, nargs=1)
@click.pass_context
def help(ctx: click.Context, topic: str | None) -> None:
    """Show help for any command."""
    # The help command implementation is taken from
    # https://www.burgundywall.com/post/having-click-help-subcommand
    if topic:
        if topic in main.commands:
            click.echo(main.commands[topic].get_help(ctx))
        else:
            raise click.UsageError(f"Unknown help topic {topic}", ctx)
    else:
        if not ctx.parent:
            raise RuntimeError("help somehow called without parent or topic")
        click.echo(ctx.parent.get_help())


@main.command()
@click.option(
    "-e",
    "--base-url",
    envvar="MONKEYFLOCKER_BASE_URL",
    default="http://localhost:8000",
    help="URL of RSP instance to dispatch mobu workers on",
)
@click.option(
    "-f",
    "--spec-file",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    envvar="MONKEYFLOCKER_SPEC_FILE",
    help="YAML spec for a monkey flock to start",
)
@click.option(
    "-k",
    "--token",
    required=True,
    envvar="MONKEYFLOCKER_TOKEN",
    help="Token to use to drive mobu",
)
@run_with_asyncio
async def start(base_url: str, spec_file: Path, token: str) -> None:
    """Start a flock of monkeys."""
    async with MonkeyflockerClient(base_url, token) as client:
        await client.start(spec_file)


@main.command()
@click.option(
    "-e",
    "--base-url",
    envvar="MONKEYFLOCKER_BASE_URL",
    default="http://localhost:8000",
    help="URL of RSP instance to dispatch mobu workers on",
)
@click.option(
    "-k",
    "--token",
    required=True,
    envvar="MONKEYFLOCKER_TOKEN",
    help="Token to use to drive mobu",
)
@click.option(
    "-o",
    "--output",
    required=True,
    type=click.Path(path_type=Path),
    envvar="MONKEYFLOCKER_OUTPUT",
    help="Directory in which to store output",
)
@click.argument("name")
@run_with_asyncio
async def report(base_url: str, token: str, output: Path, name: str) -> None:
    """Generate an output report for a flock."""
    async with MonkeyflockerClient(base_url, token) as client:
        await client.report(name, output)


@main.command()
@click.option(
    "-e",
    "--base-url",
    envvar="MONKEYFLOCKER_BASE_URL",
    default="http://localhost:8000",
    help="URL of RSP instance to dispatch mobu workers on",
)
@click.option(
    "-k",
    "--token",
    required=True,
    envvar="MONKEYFLOCKER_TOKEN",
    help="Token to use to drive mobu",
)
@click.option(
    "-o",
    "--output",
    type=click.Path(path_type=Path),
    envvar="MONKEYFLOCKER_OUTPUT",
    help="Directory in which to store output",
)
@click.argument("name")
@run_with_asyncio
async def stop(
    base_url: str, token: str, output: Path | None, name: str
) -> None:
    """Stop a flock."""
    async with MonkeyflockerClient(base_url, token) as client:
        if output:
            await client.report(name, output)
        await client.stop(name)


@main.command()
@click.option(
    "-e",
    "--base-url",
    envvar="MONKEYFLOCKER_BASE_URL",
    default="http://localhost:8000",
    help="URL of RSP instance to dispatch mobu workers on",
)
@click.option(
    "-k",
    "--token",
    required=True,
    envvar="MONKEYFLOCKER_TOKEN",
    help="Token to use to drive mobu",
)
@click.option(
    "-o",
    "--output",
    type=click.Path(path_type=Path),
    envvar="MONKEYFLOCKER_OUTPUT",
    help="Directory in which to store output",
)
@click.argument("name")
@run_with_asyncio
async def refresh(
    base_url: str, token: str, output: Path | None, name: str
) -> None:
    """Signal a flock to refresh."""
    async with MonkeyflockerClient(base_url, token) as client:
        if output:
            await client.report(name, output)
        await client.refresh(name)
