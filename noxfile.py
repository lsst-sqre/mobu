"""nox configuration for mobu."""

import shutil
import sys
from pathlib import Path

import nox
from nox.command import CommandFailed
from nox_uv import session

# Default sessions.
nox.options.sessions = ["lint", "typing", "test", "docs"]

# Other nox defaults.
nox.options.default_venv_backend = "uv"
nox.options.reuse_existing_virtualenvs = True


@session(name="coverage-report", uv_groups=["dev"])
def coverage_report(session: nox.Session) -> None:
    """Generate a code coverage report from the test suite."""
    session.run("coverage", "report", *session.posargs)


@session(uv_groups=["dev", "docs"])
def docs(session: nox.Session) -> None:
    """Build the documentation."""
    doctree_dir = (session.cache_dir / "doctrees").absolute()
    with session.chdir("docs"):
        session.run(
            "sphinx-build",
            "-W",
            "--keep-going",
            "-n",
            "-T",
            "-b",
            "html",
            "-d",
            str(doctree_dir),
            ".",
            "./_build/html",
        )


@session(name="docs-clean", uv_groups=["dev", "docs"])
def docs_clean(session: nox.Session) -> None:
    """Build the documentation without any cache."""
    if Path("docs/_build").exists():
        shutil.rmtree("docs/_build")
    if Path("docs/dev/internals").exists():
        shutil.rmtree("docs/dev/internals")
    docs(session)


@session(name="docs-linkcheck", uv_groups=["dev", "docs"])
def docs_linkcheck(session: nox.Session) -> None:
    """Check links in the documentation."""
    doctree_dir = (session.cache_dir / "doctrees").absolute()
    with session.chdir("docs"):
        try:
            session.run(
                "sphinx-build",
                "-W",
                "--keep-going",
                "-n",
                "-T",
                "-b",
                "linkcheck",
                "-d",
                str(doctree_dir),
                ".",
                "./_build/linkcheck",
            )
        except CommandFailed:
            output_path = Path("_build") / "linkcheck" / "output.txt"
            if output_path.exists():
                sys.stdout.write(output_path.read_text())
            session.error("Link check reported errors")


@session(uv_only_groups=["lint"], uv_no_install_project=True)
def lint(session: nox.Session) -> None:
    """Run pre-commit hooks."""
    session.run("prek", "run", "--all-files", *session.posargs)


@session
def run(session: nox.Session) -> None:
    """Run a local development server."""
    session.run(
        "uvicorn",
        "--reload",
        "--factory",
        "mobu.main:create_app",
    )


@session(uv_groups=["dev"])
def test(session: nox.Session) -> None:
    """Test the Semaphore server."""
    session.run(
        "pytest",
        "--cov=mobu",
        "--cov-branch",
        "--cov-report=",
        *session.posargs,
    )


@session(uv_groups=["dev", "typing"])
def typing(session: nox.Session) -> None:
    """Run mypy."""
    session.run(
        "mypy",
        *session.posargs,
        "noxfile.py",
        "src",
        "tests",
    )
