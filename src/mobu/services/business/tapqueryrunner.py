"""Run queries against a TAP service."""

from __future__ import annotations

import asyncio
import importlib.resources
import math
from typing import Any, Protocol, Union, runtime_checkable
from concurrent.futures import ThreadPoolExecutor
from random import SystemRandom
from enum import Enum
import jinja2
import pyvo
import requests
import shortuuid
import yaml
from httpx import AsyncClient
from structlog.stdlib import BoundLogger

from ...config import config
from ...exceptions import CodeExecutionError, TAPClientError
from ...models.business.tapqueryrunner import (
    TAPQueryRunnerData,
    TAPQueryRunnerOptions,
)
from ...models.user import AuthenticatedUser
from .base import Business


@runtime_checkable
class TAPQueryContext(Protocol):
    """Query Context Protocol
    Defines the methods that should be implemented for various query context implementations.
    Query context: Where/how the collection of queries to be run is generated from.
    """

    def __init__(self, **_arg: Any) -> None:
        ...

    class ContextTypes(Enum):
        """Define different types of query contexts"""

        QUERY_LIST = "QUERY_LIST"  # List of queries passed in as options
        TEMPLATES = "TEMPLATES"  # Templates from local filepath

    @property
    def context_type(self) -> TAPQueryContext.ContextTypes:
        """Get the context type"""
        ...

    def get_next_query(self) -> str:
        """Get the next query"""
        ...


class TAPQueryContextTemplates:
    """Context is template based here, i.e. the queries are read from local filepath as
    Jinja templates.
    """

    def __init__(self, taprunner: TAPQueryRunner) -> None:
        self.taprunner = taprunner

    @property
    def context_type(self) -> TAPQueryContext.ContextTypes:
        """Get Context Type

        Returns:
            TAPQueryContext.ContextTypes: The context type
        """
        return TAPQueryContext.ContextTypes.TEMPLATES

    def get_next_query(self) -> str:
        """Get a query from the query_set randomly, using the random_engine of the TAP Runner
        Render query from template, using generated parameters

        Returns:
            str: The next query string
        """
        template_name = self.taprunner.random_engine.choice(
            self.taprunner.env.list_templates(["sql"])
        )
        template = self.taprunner.env.get_template(template_name)
        query = template.render(self.taprunner.generated_params)
        return query


class TAPQueryContextQueryList:
    """Context for generating queries from a given list of query strings."""

    def __init__(self, taprunner: TAPQueryRunner) -> None:
        self.taprunner = taprunner

    @property
    def context_type(self) -> TAPQueryContext.ContextTypes:
        """Get Context Type

        Returns:
            TAPQueryContext.ContextTypes: The context type
        """
        return TAPQueryContext.ContextTypes.QUERY_LIST

    def get_next_query(self) -> str:
        """Get a query from the list randomly, using the random_engine of the TAP Runner

        Returns:
            str: The next query string
        """
        return self.taprunner.random_engine.choice(self.taprunner.queries)


# Mapping of context types to TAPQueryContext class type
TAP_QUERY_CONTEXTS = {
    TAPQueryContext.ContextTypes.QUERY_LIST: TAPQueryContextQueryList,
    TAPQueryContext.ContextTypes.TEMPLATES: TAPQueryContextTemplates,
}


class TAPQueryRunner(Business):
    """Run queries against TAP.

    Parameters
    ----------
    options
        Configuration options for the business.
    user
        User with their authentication token to use to run the business.
    http_client
        Shared HTTP client for general web access.
    logger
        Logger to use to report the results of business.
    """

    def __init__(
        self,
        options: TAPQueryRunnerOptions,
        user: AuthenticatedUser,
        http_client: AsyncClient,
        logger: BoundLogger,
    ) -> None:
        super().__init__(options, user, http_client, logger)
        self._running_query: str | None = None
        self._client: pyvo.dal.TAPService | None = None
        self._random = SystemRandom()
        self._pool = ThreadPoolExecutor(max_workers=1)
        self._context = self._get_context(options)
        self._env = self._get_environment()
        self._params = self._get_params()
        self._queries = options.queries

    async def startup(self) -> None:
        if self._context.context_type is TAPQueryContext.ContextTypes.TEMPLATES:
            templates = self._env.list_templates(["sql"])
            self.logger.info("Query templates to choose from: %s", templates)
        with self.timings.start("make_client"):
            self._client = self._make_client(self.user.token)

    def get_next_query(self) -> str:
        """Get the next query string from the context

        Returns:
            str: The next query string
        """
        return self._context.get_next_query()

    @property
    def queries(self):
        return self._queries

    @property
    def env(self):
        return self._env

    @property
    def random_engine(self):
        return self._random

    @property
    def params(self):
        return self._params

    @property
    def generated_params(self):
        return self._generate_parameters()

    def _get_context(
        self,
        options,
    ) -> Union[TAPQueryContextQueryList, TAPQueryContextTemplates]:
        """Get the context for this TAP query runner

        Parameters:
            options (TAPQueryRunnerOptions): The runner options based on which to get the context
        """
        if options.queries:
            return TAP_QUERY_CONTEXTS[TAPQueryContext.ContextTypes.QUERY_LIST](
                taprunner=self
            )
        return TAP_QUERY_CONTEXTS[TAPQueryContext.ContextTypes.TEMPLATES](
            taprunner=self
        )

    def _get_environment(self) -> Union[jinja2.Environment, None]:
        """Get the jinha2 template if applicable else return None

        Returns:
            Union[jinja2.Environment, None]: Return the jinja2 Environment, or None
        """
        if self._context.context_type is not TAPQueryContext.ContextTypes.TEMPLATES:
            return None

        # Load templates and parameters. The path has to be specified in two
        # different ways: as a relative path for Jinja's PackageLoader, and as
        # a sequence of joinpath operations for importlib.resources.
        template_path = ("data", "tapqueryrunner", self.options.query_set)
        env = jinja2.Environment(
            loader=jinja2.PackageLoader("mobu", "/".join(template_path)),
            undefined=jinja2.StrictUndefined,
            autoescape=jinja2.select_autoescape(disabled_extensions=["sql"]),
        )
        return env

    def _get_params(self) -> Union[dict, None]:
        """Get the parameters as a dictionary if applicable else return None

        Returns:
            Union[dict, None]: Return the parameters as a dict, or None
        """
        if self._context.context_type is not TAPQueryContext.ContextTypes.TEMPLATES:
            return None
        template_path = ("data", "tapqueryrunner", self.options.query_set)
        files = importlib.resources.files("mobu")
        for directory in template_path:
            files = files.joinpath(directory)
        with files.joinpath("params.yaml").open("r") as f:
            params = yaml.safe_load(f)
        return params

    async def execute(self) -> None:
        """Get and execute the next query from the context, synchronously or asynchronously
        depending on options
        """
        query = self.get_next_query()
        with self.timings.start("execute_query", {"query": query}) as sw:
            self._running_query = query

            try:
                if self.options.sync:
                    await self.run_sync_query(query)
                else:
                    await self.run_async_query(query)
            except Exception as e:
                raise CodeExecutionError(
                    user=self.user.username,
                    code=query,
                    code_type="TAP query",
                    error=f"{type(e).__name__}: {e!s}",
                ) from e

            self._running_query = None
            elapsed = sw.elapsed.total_seconds()

        self.logger.info(f"Query finished after {elapsed} seconds")

    async def run_async_query(self, query: str) -> None:
        """Run the query asynchronously

        Parameters:
            query (str): The query string to execute
        """
        if not self._client:
            raise RuntimeError("TAPQueryRunner startup never ran")
        self.logger.info("Running (async): %s", query)
        job = self._client.submit_job(query)
        try:
            job.run()
            while job.phase not in ("COMPLETED", "ERROR"):
                await asyncio.sleep(30)
        finally:
            job.delete()

    async def run_sync_query(self, query: str) -> None:
        """Run the query synchronously

        Parameters:
            query (str): The query string to execute
        """
        if not self._client:
            raise RuntimeError("TAPQueryRunner startup never ran")
        self.logger.info("Running (sync): %s", query)
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(self._pool, self._client.search, query)

    def dump(self) -> TAPQueryRunnerData:
        return TAPQueryRunnerData(
            running_query=self._running_query, **super().dump().dict()
        )

    def _make_client(self, token: str) -> pyvo.dal.TAPService:
        if not config.environment_url:
            raise RuntimeError("environment_url not set")
        tap_url = str(config.environment_url).rstrip("/") + "/api/tap"
        try:
            s = requests.Session()
            s.headers["Authorization"] = "Bearer " + token
            auth = pyvo.auth.AuthSession()
            auth.credentials.set("lsst-token", s)
            auth.add_security_method_for_url(tap_url, "lsst-token")
            auth.add_security_method_for_url(tap_url + "/sync", "lsst-token")
            auth.add_security_method_for_url(tap_url + "/async", "lsst-token")
            auth.add_security_method_for_url(tap_url + "/tables", "lsst-token")
            return pyvo.dal.TAPService(tap_url, auth)
        except Exception as e:
            raise TAPClientError(e, user=self.user.username) from e

    def _generate_random_polygon(
        self,
        *,
        min_ra: float,
        max_ra: float,
        min_dec: float,
        max_dec: float,
        min_radius: float,
        radius_range: float,
    ) -> str:
        """Generate a random polygon as comma-separated ra/dec values."""
        ra = min_ra + self._random.random() * (max_ra - min_ra)
        dec = min_dec + self._random.random() * (max_dec - min_dec)
        r = min_radius + self._random.random() * radius_range
        n = self._random.randrange(3, 8)
        phi = self._random.random() * 2 * math.pi
        poly = []
        for theta in [phi + i * 2 * math.pi / n for i in range(n)]:
            poly.append(ra + r * math.sin(theta))
            poly.append(dec + r * math.cos(theta))
        return ", ".join([str(x) for x in poly])

    def _generate_parameters(self) -> dict[str, int | float | str]:
        """Generate some random parameters for the query."""
        min_ra = self._params.get("min_ra", 55.0)
        max_ra = self._params.get("max_ra", 70.0)
        min_dec = self._params.get("min_dec", -42.0)
        max_dec = self._params.get("max_dec", -30.0)
        min_radius = self._params.get("min_radius", 0.01)
        radius_range = self._params.get("radius_range", 0.04)
        radius_near_range = self._params.get("radius_near_range", 0.09)
        min_flux = 0.0 + self._random.random() * 0.00100
        min_mag = 15.0 + self._random.random() * 15.0
        result = {
            "ra": min_ra + self._random.random() * (max_ra - min_ra),
            "dec": min_dec + self._random.random() * (max_dec - min_dec),
            "min_flux": min_flux,
            "max_flux": min_flux + 0.00001,
            "min_mag": min_mag,
            "max_mag": min_mag + 0.1,
            "polygon": self._generate_random_polygon(
                min_ra=min_ra,
                max_ra=max_ra,
                min_dec=min_dec,
                max_dec=max_dec,
                min_radius=min_radius,
                radius_range=radius_range,
            ),
            "radius": min_radius + self._random.random() * radius_range,
            "radius_near": (min_radius + self._random.random() * radius_near_range),
            "username": self.user.username,
            "query_id": "mobu-" + shortuuid.uuid(),
        }
        object_ids = self._params.get("object_ids")
        if object_ids:
            result["object"] = str(self._random.choice(object_ids))
            result["objects"] = ", ".join(
                str(o) for o in self._random.choices(object_ids, k=12)
            )
        return result
