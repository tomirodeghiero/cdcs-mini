"""Reporter interface.

A reporter turns a ``Report`` into a string (and gives back a dict view
for in-process consumers like the HTTP layer). Adding YAML, HTML or
anything else just means implementing this protocol.
"""

from __future__ import annotations

from typing import Protocol

from cdcs_mini.domain.models import Report
from cdcs_mini.reporting.schema import ReportDict


class Reporter(Protocol):
    def render(self, report: Report) -> str: ...

    def to_dict(self, report: Report) -> ReportDict: ...
