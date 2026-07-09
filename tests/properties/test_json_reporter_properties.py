"""Property-based tests for the JSON reporter.

The reporter's job is to be a deterministic, lossless serializer for the
in-memory ``Report`` graph. Two invariants follow:

* ``render`` is pure — the same report renders to byte-identical JSON.
* the rendered JSON, once parsed back with ``json.loads``, equals the
  ``to_dict(report)`` dictionary. There is no information loss between
  the in-memory shape and the wire shape.
"""

from __future__ import annotations

import json

from hypothesis import given, settings

from cdcs.domain.models import Report
from cdcs.reporting.json_reporter import JsonReporter
from tests.properties._strategies import reports


@given(report=reports())
@settings(max_examples=150, deadline=None)
def test_render_is_deterministic(report: Report) -> None:
    reporter = JsonReporter()
    assert reporter.render(report) == reporter.render(report)


@given(report=reports())
@settings(max_examples=150, deadline=None)
def test_render_round_trips_through_json(report: Report) -> None:
    """``json.loads(render(report)) == to_dict(report)``."""

    reporter = JsonReporter()
    payload = reporter.render(report)
    decoded = json.loads(payload)
    assert decoded == reporter.to_dict(report)


@given(report=reports())
@settings(max_examples=150, deadline=None)
def test_indent_setting_does_not_change_semantics(report: Report) -> None:
    """Pretty-printed and compact JSON deserialize to the same object."""

    pretty = json.loads(JsonReporter(indent=2).render(report))
    compact = json.loads(JsonReporter(indent=None).render(report))
    assert pretty == compact
