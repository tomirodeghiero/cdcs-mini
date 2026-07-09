"""Language-agnostic protocols for the DSL parser and validators.

The DSL itself ("@generate", behavior/examples/constraints/calls/reads,
``==`` and ``raises``) is identical across languages — only the
*expressions* inside the DSL change shape. ``ExpressionParser`` is the
seam: it knows how to validate that a string is a syntactically valid
expression in the host language, and which identifiers it references.

``LanguageAdapter`` bundles the per-language concerns the rest of the
pipeline needs at construction time. Today the only concrete adapter is
``PythonAdapter``; a ``TypeScriptAdapter`` will land in a later phase.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from cdcs.domain.models import Parameter

if TYPE_CHECKING:
    from cdcs.parsing.source_parser import ParsedSource
    from cdcs.synthesis.prompt import LanguageProfile


@runtime_checkable
class ExpressionParser(Protocol):
    """Language-specific expression and annotation parsing for the DSL.

    Implementations are stateless and reusable across DSL invocations.
    Every method returns ``None`` (or False) when the input cannot be
    parsed as a valid expression in the host language — never raises,
    so the DSL parser can convert it into a ``MalformedDSLError``
    diagnostic with line info.
    """

    def extract_identifiers(self, expression: str) -> frozenset[str] | None:
        """Names referenced inside an expression, excluding callee names.

        For ``foo(x, y)`` returns ``{"x", "y"}`` — ``foo`` is the callee,
        not a parameter reference. ``None`` means the expression itself
        was unparseable.
        """
        ...

    def extract_call_target(self, expression: str) -> str | None:
        """Name of the function being called in ``foo(args)``.

        ``None`` when the expression is not a single bare call (e.g. it
        is ``obj.method(x)`` or a binary op) or when it doesn't parse.
        """
        ...

    def is_valid_annotation(self, annotation: str) -> bool:
        """True if ``annotation`` parses as a valid type annotation."""
        ...

    def parse_parameter_list(self, params_text: str) -> tuple[Parameter, ...] | None:
        """Parse a comma-separated parameter list (the body of a callable
        signature's parentheses) into ``Parameter`` tuples.

        ``None`` when the list cannot be parsed in the host language.
        """
        ...


@runtime_checkable
class SourceParserProtocol(Protocol):
    """Walks a source file and yields :class:`ParsedSource`.

    Each language implementation reads its host-language syntax through
    whatever parser is appropriate (``ast`` for Python, the TS Compiler
    API for TypeScript) and returns the same structural shape so
    :class:`ReportService` can consume both.
    """

    def parse(self, source: str, *, filename: str = "<input>") -> ParsedSource: ...


@runtime_checkable
class LanguageAdapter(Protocol):
    """Per-language settings the pipeline needs at construction time.

    Adapters are immutable value objects (typically frozen dataclasses).
    Future phases will extend this Protocol with ``source_parser``,
    ``prompt_builder`` and ``gate_chain_factory`` as the second language
    arrives; keeping the surface narrow today avoids forcing those
    abstractions before we have two real consumers to validate them.
    """

    @property
    def name(self) -> str:
        """Stable identifier for the language (``"python"``, ``"typescript"``)."""
        ...

    @property
    def source_extensions(self) -> frozenset[str]:
        """File extensions that this adapter claims for autodetection."""
        ...

    @property
    def impl_artifact_suffix(self) -> str:
        """Suffix appended to ``{source_stem}`` for the generated impl file."""
        ...

    @property
    def test_artifact_suffix(self) -> str:
        """Suffix appended to ``test_{source_stem}`` for the generated tests."""
        ...

    @property
    def expression_parser(self) -> ExpressionParser:
        """The parser used by the DSL to validate inline expressions."""
        ...

    @property
    def source_parser(self) -> SourceParserProtocol:
        """Walks source files in this language. See :class:`SourceParserProtocol`."""
        ...

    @property
    def known_globals(self) -> frozenset[str]:
        """Identifiers that count as "known" beyond declared parameters.

        Used by ``validate_known_parameters`` so the validator doesn't
        flag references to language built-ins (``len``, ``int``, ...) as
        unknown parameters.
        """
        ...

    @property
    def receiver_parameter_name(self) -> str:
        """Host-language name for the implicit instance receiver.

        The DSL always writes ``self.X`` in ``calls:``/``reads:`` as the
        canonical receiver-prefix (PDF §4). The validator translates
        that to the host language's actual receiver — ``"self"`` for
        Python, ``"this"`` for TypeScript — when checking that the
        function's signature actually declares one.
        """
        ...

    @property
    def prompt_profile(self) -> LanguageProfile:
        """Text fragments / renderers the prompt builder needs.

        See :class:`cdcs.synthesis.prompt.LanguageProfile`. The
        profile is what turns "synthesize a function" into either a
        Python or a TypeScript prompt.
        """
        ...
