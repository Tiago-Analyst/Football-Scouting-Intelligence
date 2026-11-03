"""Every sentence the API decides arrives with the values its words need.

WHAT WENT WRONG

`messages.json` held `"{count} {noun}"`. The API sent
`{"count": 16, "noun_key": "dribbles_attempted", "threshold": 30}`. The names
did not match, so the placeholder was never filled and the reader was shown

    Low evidence - 16 {noun}

in English and in Portuguese alike. It had been live for as long as the
mechanism had existed.

Nothing caught it. There was a test asserting every code the backend can emit
has copy on both sides, and a test asserting the two languages interpolate the
same placeholders - and both passed, because the copy existed and both
languages were wrong in exactly the same way. The contract nobody was checking
is the one between the template's placeholder names and the keys of the dict
the API sends.

WHY THIS IS A PYTHON TEST

The frontend owns rendering and tests it by calling the renderer. This half is
about what the backend SENDS, and reading that out of Python needs Python: the
`Message(` call sites include a conditional code, dicts built over several
statements, and a pair returned from a module that deliberately knows nothing
about the schema. A regex over the source either misses those - silently, which
reads as a pass - or sweeps up things that are not messages. `ast` does not
guess.

WHAT IT CANNOT SEE, AND WHY THAT IS WRITTEN DOWN

Some call sites take both the code and the values from runtime data - the
stored quality rows are the clearest case, where the values were written to the
database by a pipeline run. Those are named in `UNRESOLVED` with their reason,
and the test asserts the list is exactly right. A new unverifiable call site
therefore fails here rather than joining them unnoticed.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1] / "app"
DICTIONARIES = Path(__file__).resolve().parents[2] / "frontend" / "src" / "i18n" / "dictionaries"

#: Call sites whose code or values are runtime data rather than written down.
#:
#: Each entry is `module:line-ish identity` as the extractor reports it. The
#: point of pinning them is not that they are acceptable - it is that the set
#: stops growing without somebody saying so.
UNRESOLVED: frozenset[str] = frozenset(
    {
        # The stored quality rows: a pipeline run wrote both the code and the
        # values, and the route passes them through. Covered instead by the
        # quality report's own tests, which build the findings.
        "api/v1/quality.py",
        # Composed in `app/analytics/interpretation.py` as (code, values)
        # pairs and wrapped here. The pairs themselves are resolved below.
        "api/v1/players.py",
        # `health.py` assembles its own pairs the same way.
        "api/v1/health.py",
        # The route wrapping `RankingAdjustment.explain_code`, whose pair is
        # resolved below.
        "api/v1/messages.py",
    }
)


def templates(locale: str) -> dict[str, str]:
    return json.loads((DICTIONARIES / locale / "messages.json").read_text(encoding="utf-8"))


def placeholders(template: str) -> set[str]:
    return set(re.findall(r"\{(\w+)\}", template))


def _dict_keys(node: ast.AST) -> set[str] | None:
    """The literal string keys of a dict literal, or None if it is not one.

    None rather than an empty set: a dict whose keys are computed supplies
    names this test cannot name, and reporting that as "supplies nothing"
    would fail an innocent call site.
    """
    if not isinstance(node, ast.Dict):
        return None
    keys: set[str] = set()
    for key in node.keys:
        if isinstance(key, ast.Constant) and isinstance(key.value, str):
            keys.add(key.value)
        else:
            return None
    return keys


def _codes(node: ast.AST) -> set[str] | None:
    """Every code a `code=` expression can evaluate to."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return {node.value}
    if isinstance(node, ast.IfExp):
        left, right = _codes(node.body), _codes(node.orelse)
        if left is None or right is None:
            return None
        return left | right
    return None


class _Suppliers(ast.NodeVisitor):
    """What each code is given, read out of one module.

    Two shapes are understood.

    `Message(code=..., values={...})`, the common one, including the
    conditional code: `code="low_evidence_count" if low else "evidence_count"`
    gives both codes the same dict.

    A dict built up over several statements and then handed over by name. This
    is `RankingAdjustment.explain_code`, which returns `(code, values)` rather
    than a `Message` so that the analytics layer keeps knowing nothing about
    the API schema - and which adds `minutes` to the dict on one branch only.
    That last detail is the whole reason the name has to be followed rather
    than the call site read in isolation.
    """

    def __init__(self, known: set[str]) -> None:
        self.known = known
        self.supplied: dict[str, list[set[str]]] = {}
        self.unresolved: set[str] = set()
        self._dicts: dict[str, set[str]] = {}

    # -- following a named dict ---------------------------------------------

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        outer = self._dicts
        self._dicts = {}
        self.generic_visit(node)
        self._dicts = outer

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            if isinstance(target, ast.Name):
                keys = _dict_keys(node.value)
                if keys is not None:
                    self._dicts[target.id] = set(keys)
            elif (
                isinstance(target, ast.Subscript)
                and isinstance(target.value, ast.Name)
                and isinstance(target.slice, ast.Constant)
                and isinstance(target.slice.value, str)
                and target.value.id in self._dicts
            ):
                self._dicts[target.value.id].add(target.slice.value)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if isinstance(node.target, ast.Name) and node.value is not None:
            keys = _dict_keys(node.value)
            if keys is not None:
                self._dicts[node.target.id] = set(keys)
        self.generic_visit(node)

    # -- the two supplier shapes --------------------------------------------

    def visit_Return(self, node: ast.Return) -> None:
        # `return ("code", values)` - a pair destined to become a Message.
        value = node.value
        if isinstance(value, ast.Tuple) and len(value.elts) == 2:
            codes = _codes(value.elts[0])
            if codes and codes <= self.known:
                self._record(codes, value.elts[1])
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name) and node.func.id == "Message":
            code_arg = next((k.value for k in node.keywords if k.arg == "code"), None)
            values_arg = next((k.value for k in node.keywords if k.arg == "values"), None)
            codes = _codes(code_arg) if code_arg is not None else None
            if codes is None:
                self.unresolved.add("")
            else:
                # No `values=` at all is a supplier of nothing, which is a
                # claim this test should check rather than skip.
                self._record(codes, values_arg)
        self.generic_visit(node)

    def _record(self, codes: set[str], values: ast.AST | None) -> None:
        if values is None:
            keys: set[str] | None = set()
        else:
            keys = _dict_keys(values)
            if keys is None and isinstance(values, ast.Name):
                keys = self._dicts.get(values.id)
        if keys is None:
            self.unresolved.add("")
            return
        for code in codes:
            self.supplied.setdefault(code, []).append(set(keys))


def collect() -> tuple[dict[str, list[set[str]]], set[str]]:
    known = set(templates("en"))
    supplied: dict[str, list[set[str]]] = {}
    unresolved: set[str] = set()
    for path in sorted(BACKEND.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        visitor = _Suppliers(known)
        visitor.visit(ast.parse(path.read_text(encoding="utf-8")))
        for code, shapes in visitor.supplied.items():
            supplied.setdefault(code, []).extend(shapes)
        if visitor.unresolved:
            unresolved.add(path.relative_to(BACKEND).as_posix())
    return supplied, unresolved


@pytest.fixture(scope="module")
def collected() -> tuple[dict[str, list[set[str]]], set[str]]:
    return collect()


class TestTheExtractorSeesWhatItClaimsTo:
    """A guard over the guard.

    An extractor that finds nothing makes every assertion below vacuous, and
    that is the failure mode this kind of test has. The sibling extractor in
    `i18n-messages.test.mjs` has been wrong twice - once too narrow, silently -
    which is why both of them are pinned.
    """

    def test_it_finds_the_message_the_bug_was_in(
        self, collected: tuple[dict[str, list[set[str]]], set[str]]
    ) -> None:
        supplied, _ = collected
        assert "evidence_count" in supplied
        assert any({"count", "noun_key", "threshold"} <= s for s in supplied["evidence_count"])

    def test_it_follows_a_conditional_code(
        self, collected: tuple[dict[str, list[set[str]]], set[str]]
    ) -> None:
        # One `Message(` call, two codes: the dict must be credited to both.
        supplied, _ = collected
        assert "low_evidence_count" in supplied
        assert "evidence_count" in supplied

    def test_it_follows_a_dict_built_over_several_statements(
        self, collected: tuple[dict[str, list[set[str]]], set[str]]
    ) -> None:
        # `explain_code` assigns the dict, then adds `minutes` on one branch.
        # Reading the return in isolation would miss `minutes` entirely.
        supplied, _ = collected
        shapes = supplied.get("ranking_shrunk", [])
        assert shapes, "the (code, values) pair form is no longer found"
        assert any("minutes" in s for s in shapes)

    def test_it_finds_a_useful_number_of_codes(
        self, collected: tuple[dict[str, list[set[str]]], set[str]]
    ) -> None:
        supplied, _ = collected
        assert len(supplied) >= 30, f"only {len(supplied)} codes resolved"


class TestEveryPlaceholderIsSupplied:
    """The contract the `{noun}` defect broke."""

    @pytest.mark.parametrize("locale", ["en", "pt"])
    def test_no_template_names_a_value_the_api_does_not_send(
        self, locale: str, collected: tuple[dict[str, list[set[str]]], set[str]]
    ) -> None:
        supplied, _ = collected
        copy = templates(locale)
        unfilled: list[str] = []
        for code, shapes in sorted(supplied.items()):
            template = copy.get(code)
            if template is None:
                continue
            needed = placeholders(template)
            for shape in shapes:
                missing = needed - shape
                if missing:
                    unfilled.append(
                        f"{code} never receives {sorted(missing)} (gets {sorted(shape)})"
                    )
        assert unfilled == [], "\n".join(unfilled)

    def test_a_resolved_code_without_copy_is_a_missing_translation(
        self, collected: tuple[dict[str, list[set[str]]], set[str]]
    ) -> None:
        # The sibling test asserts this from the other side; asserting it here
        # too is what stops `test_no_template_names_a_value...` passing because
        # `copy.get(code)` was None for every code.
        supplied, _ = collected
        en = templates("en")
        assert [c for c in supplied if c not in en] == []


class TestWhatCannotBeReadIsWrittenDown:
    def test_the_unresolved_call_sites_are_exactly_the_known_ones(
        self, collected: tuple[dict[str, list[set[str]]], set[str]]
    ) -> None:
        _, unresolved = collected
        assert unresolved == set(UNRESOLVED), (
            f"appeared: {sorted(unresolved - UNRESOLVED)}; gone: {sorted(UNRESOLVED - unresolved)}"
        )


class TestTheNounIsAlwaysAKey:
    """The second half of the same defect.

    The interface composes `low_evidence_title` itself and used to pass the
    configured English plural - "dribbles attempted" - under the name `noun`.
    The glossary is keyed `dribbles_attempted`, so the lookup missed and the
    English went into a Portuguese tooltip. Both halves came from one name
    that did not say whether it carried a word or an identifier.
    """

    @pytest.mark.parametrize("locale", ["en", "pt"])
    def test_no_template_asks_for_a_bare_noun(self, locale: str) -> None:
        offenders = [
            code for code, template in templates(locale).items() if "noun" in placeholders(template)
        ]
        assert offenders == [], (
            f"{offenders} name a placeholder `noun`; the glossary is keyed by the "
            "underscored identifier, so the value must be `noun_key`"
        )

    def test_the_api_sends_the_key_beside_the_prose(self) -> None:
        schema = (BACKEND / "schemas" / "api.py").read_text(encoding="utf-8")
        assert "noun_key: str" in schema, "the interface is deriving the key again"
