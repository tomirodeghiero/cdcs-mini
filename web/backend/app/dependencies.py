"""Dependency providers.

Endpoints pull the service and the reporter via ``ServiceDep`` /
``ReporterDep`` rather than reaching for module-level singletons.
That's what makes them easy to override from tests::

    app.dependency_overrides[get_reporter] = lambda: my_fake
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from cdcs_mini.application.report_service import ReportService
from cdcs_mini.reporting.base import Reporter
from cdcs_mini.reporting.json_reporter import JsonReporter


@lru_cache(maxsize=1)
def get_service() -> ReportService:
    return ReportService.default()


@lru_cache(maxsize=1)
def get_reporter() -> Reporter:
    return JsonReporter()


ServiceDep = Annotated[ReportService, Depends(get_service)]
ReporterDep = Annotated[Reporter, Depends(get_reporter)]
