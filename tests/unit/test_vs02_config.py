"""
VS02-M2 pipeline rules: the authored file, its loader, and the methodology
digest with its pin (plan A22.3; coverage row C-18).

The methodology digest identifies everything able to change a figure: the
file's closed stages and eight constants in code. Its canonical form is
frozen by plan A22.3 item 3 (OD-1), so nothing here is proved through the
code it is about. The canonical text is written out in this file exactly as
the plan prints it, and the pinned digest is the SHA-256 of that text,
derived outside the application with `shasum` and `openssl` from the plan's
own line.

Every refusal is compared on its whole message with the file's own path
removed, because a path can spell a key by accident. Where the plan is
silent on a file's form, the loader refuses rather than interprets, and the
test says which rule it is pinning.
"""

from __future__ import annotations

import ast
import decimal
import hashlib
import os
import re
import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from decimal import (
    ROUND_CEILING,
    ROUND_DOWN,
    ROUND_HALF_EVEN,
    ROUND_HALF_UP,
    ROUND_UP,
    Context,
    Decimal,
    Inexact,
    Rounded,
    Subnormal,
    Underflow,
    localcontext,
)
from pathlib import Path

import pytest
import yaml

from app.fx.convert import ARITHMETIC_PRECISION, BASE_QUANTUM, ROUNDING_MODE
from app.normalization.config import default_config
from app.pipeline import config as config_module
from app.pipeline.aggregation import CONCENTRATION_TOP_N, CUMULATIVE_POINTS, PERIOD_HORIZON
from app.pipeline.config import (
    DEFAULT_PIPELINE_RULES_PATH,
    PipelineRules,
    default_pipeline_rules,
    load_pipeline_rules,
)
from app.pipeline.errors import PipelineConfigError, PipelineError
from app.pipeline.measures import SHARE_QUANTUM, WEIGHT_QUANTUM

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[2]

#: Plan A22.3 item 4: pipeline_version -> methodology digest. An entry is
#: NEVER edited or removed; a new pipeline_version adds an entry. Changing a
#: constant or closed_stages without a new version therefore fails the build
#: here. This entry covers all eight constants, so VS02-M3 adds none (OD-2).
PINNED_METHODOLOGIES = {
    1: "8e929564987c0ea7a317c81c31c0a541ca70017337590b93731b77aa32cbeecf",
}
PIN = PINNED_METHODOLOGIES[1]

#: Plan A22.3 item 3: the canonical text for pipeline_version 1, exactly as
#: the plan prints it. One line of 235 ASCII characters.
CANONICAL_METHODOLOGY_1 = (
    '{"arithmetic_precision":"50","base_quantum":"0.01","closed_stages":["won"],'
    '"concentration_top_n":"5","cumulative_points":["1","3","5"],"period_horizon":"12",'
    '"rounding":"ROUND_HALF_EVEN","share_quantum":"0.0001","weight_quantum":"0.01"}'
)
#: The nine keys of the methodology object, as the plan's table lists them.
METHODOLOGY_KEYS = ["arithmetic_precision", "base_quantum", "closed_stages", "concentration_top_n",
                    "cumulative_points", "period_horizon", "rounding", "share_quantum",
                    "weight_quantum"]

#: The committed file as plain values, written out here.
VALID = {"version": 1, "pipeline_version": 1, "closed_stages": ["won"]}

FILE = "<file>"
VERSION_REFUSED = f"{FILE}: pipeline_version: expected an integer of at least 1"
STAGES_REFUSED = f"{FILE}: closed_stages: expected a non-empty list of stage values"

#: Decimal contexts a caller could be in when the digest is computed.
AMBIENT = [
    Context(prec=1, rounding=ROUND_UP),
    Context(prec=2, rounding=ROUND_DOWN, traps=[Inexact, Rounded]),
    Context(prec=1, rounding=ROUND_CEILING, Emin=-1, Emax=1, traps=[]),
    Context(prec=2, rounding=ROUND_HALF_UP, Emin=-2, Emax=2, traps=[]),
    Context(prec=1, Emin=-1, Emax=1, traps=[Subnormal, Underflow, Inexact, Rounded]),
]
AMBIENT_IDS = ["one digit", "inexact and rounded trapped", "exponents of one, no trap",
               "exponents of two, no trap", "exponents of one, every loss trapped"]
#: What a process could have done to decimal's own default context, from
#: which a Context(...) call takes every field it does not state.
SABOTAGE = [{"prec": 1, "rounding": ROUND_UP}, {"Emax": 1}, {"Emin": -1}, {"clamp": 1},
            {"traps": True}, {"traps": False}]


def write_text(tmp_path: Path, text: str) -> Path:
    """One candidate file, under a name that spells no key of the rules."""
    path = tmp_path / "candidate.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def write(tmp_path: Path, data: object) -> Path:
    text = yaml.safe_dump(data, sort_keys=False)
    assert yaml.safe_load(text) == data, "the fixture must reach the loader as it was written"
    return write_text(tmp_path, text)


def candidate(tmp_path: Path, **overrides: object) -> Path:
    return write(tmp_path, {**VALID, **overrides})


def load_with(tmp_path: Path, **overrides: object) -> PipelineRules:
    return load_pipeline_rules(candidate(tmp_path, **overrides))


def refusal(path: Path) -> str:
    """Why a file is refused: the whole message, with the file's own path replaced."""
    with pytest.raises(PipelineConfigError) as refused:
        load_pipeline_rules(path)
    assert not isinstance(refused.value, PipelineError), "a refused file is not a data error"
    assert str(path) in str(refused.value), "a refusal names the file it refuses"
    return str(refused.value).replace(str(path), FILE)


@contextmanager
def process_default(**changes: object) -> Iterator[None]:
    """decimal.DefaultContext with some fields changed, and put back whatever happens."""
    default = decimal.DefaultContext
    kept = (default.prec, default.rounding, default.Emin, default.Emax, default.clamp,
            dict(default.traps))
    try:
        for name, value in changes.items():
            if name == "traps":
                for signal in kept[5]:
                    default.traps[signal] = value
            else:
                setattr(default, name, value)
        yield
    finally:
        default.prec, default.rounding, default.Emin, default.Emax, default.clamp = kept[:5]
        for signal, value in kept[5].items():
            default.traps[signal] = value


@pytest.fixture
def committed() -> PipelineRules:
    """The committed rules, loaded from their file and not from the process cache."""
    return load_pipeline_rules(DEFAULT_PIPELINE_RULES_PATH)


@pytest.fixture
def fresh_default():
    """default_pipeline_rules() with an empty cache before the test and after it."""
    default_pipeline_rules.cache_clear()
    yield
    default_pipeline_rules.cache_clear()


# ---------------------------------------------------------------------------
# The committed file (plan A22.3)
# ---------------------------------------------------------------------------


def test_the_committed_file_is_authored_exactly_as_the_plan_records_it():
    text = DEFAULT_PIPELINE_RULES_PATH.read_text(encoding="utf-8")

    assert yaml.safe_load(text) == VALID
    assert list(yaml.safe_load(text)) == ["version", "pipeline_version", "closed_stages"]
    assert [line for line in text.splitlines() if line and not line.startswith("#")] == [
        "version: 1            # file format",
        "pipeline_version: 1   # bumped whenever anything that can change a figure changes",
        "closed_stages: [won]  # each must be a D1 stage value",
    ]


def test_the_committed_rules_hold_their_two_authored_values(committed):
    assert committed == PipelineRules(pipeline_version=1, closed_stages=frozenset({"won"}))
    assert type(committed.pipeline_version) is int
    assert type(committed.closed_stages) is frozenset


def test_the_rules_cannot_be_changed_after_they_are_loaded(committed):
    with pytest.raises(AttributeError):
        committed.pipeline_version = 2  # type: ignore[misc]
    with pytest.raises(AttributeError):
        committed.closed_stages.add("negotiation")  # type: ignore[attr-defined]


def test_the_default_path_is_the_committed_file_where_the_image_copies_it():
    assert DEFAULT_PIPELINE_RULES_PATH == REPO / "config" / "intelligence" / "pipeline_rules.yaml"
    assert DEFAULT_PIPELINE_RULES_PATH.is_file()


def test_the_file_names_no_rate_set_version(tmp_path):
    """Plan A7.3 and A22.3 item 1: fx_rates.yaml is the one place a rate set is named."""
    assert "rate_set_version" not in yaml.safe_load(
        DEFAULT_PIPELINE_RULES_PATH.read_text(encoding="utf-8"))
    assert refusal(candidate(tmp_path, rate_set_version="1")) == (
        f"{FILE}: missing keys [], unknown keys ['rate_set_version']")


# ---------------------------------------------------------------------------
# The eight constants (plan A22.3 item 2, OD-2)
# ---------------------------------------------------------------------------

#: Each constant, the module that defines it, and its final value as text.
CONSTANTS = {
    "ARITHMETIC_PRECISION": ("app/fx/convert.py", "50"),
    "ROUNDING_MODE": ("app/fx/convert.py", "ROUND_HALF_EVEN"),
    "BASE_QUANTUM": ("app/fx/convert.py", "0.01"),
    "WEIGHT_QUANTUM": ("app/pipeline/measures.py", "0.01"),
    "SHARE_QUANTUM": ("app/pipeline/measures.py", "0.0001"),
    "PERIOD_HORIZON": ("app/pipeline/aggregation.py", "12"),
    "CONCENTRATION_TOP_N": ("app/pipeline/aggregation.py", "5"),
    "CUMULATIVE_POINTS": ("app/pipeline/aggregation.py", "(1, 3, 5)"),
}


def _assignments(name: str) -> list[str]:
    """Every file of the two packages that assigns the name at any level."""
    found = []
    for path in sorted([*(REPO / "app" / "fx").rglob("*.py"),
                        *(REPO / "app" / "pipeline").rglob("*.py")]):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            targets: list[ast.expr] = []
            if isinstance(node, ast.Assign):
                targets = node.targets
            elif isinstance(node, ast.AnnAssign | ast.AugAssign | ast.NamedExpr):
                targets = [node.target]
            found += [path.relative_to(REPO).as_posix() for target in targets
                      if isinstance(target, ast.Name) and target.id == name]
    return found


def test_all_eight_constants_exist_with_their_final_values():
    """OD-2: the three of M1 and the five of this package, as the plan states them."""
    assert {
        "ARITHMETIC_PRECISION": str(ARITHMETIC_PRECISION), "ROUNDING_MODE": ROUNDING_MODE,
        "BASE_QUANTUM": str(BASE_QUANTUM), "WEIGHT_QUANTUM": str(WEIGHT_QUANTUM),
        "SHARE_QUANTUM": str(SHARE_QUANTUM), "PERIOD_HORIZON": str(PERIOD_HORIZON),
        "CONCENTRATION_TOP_N": str(CONCENTRATION_TOP_N),
        "CUMULATIVE_POINTS": str(CUMULATIVE_POINTS),
    } == {name: value for name, (_, value) in CONSTANTS.items()}
    assert ROUNDING_MODE is ROUND_HALF_EVEN


@pytest.mark.parametrize("name", sorted(CONSTANTS))
def test_each_constant_is_defined_once_and_never_restated(name):
    """
    Plan A22.3 item 2: M1's three are imported and never restated, and the
    other five are each defined once. The digest's module defines none.
    """
    assert _assignments(name) == [CONSTANTS[name][0]]


def test_the_digest_reads_the_constants_themselves_and_restates_none():
    """Plan A22.3 item 3, "live values": imported by name, from where each is defined."""
    tree = ast.parse((REPO / "app" / "pipeline" / "config.py").read_text(encoding="utf-8"))
    imported = {alias.name: node.module for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom) for alias in node.names}

    assert {name: imported.get(name) for name in CONSTANTS} == {
        name: path.removesuffix(".py").replace("/", ".") for name, (path, _) in CONSTANTS.items()}
    constants = {node.value for node in ast.walk(tree) if isinstance(node, ast.Constant)}
    assert not {"50", "0.01", "0.0001", "12", "5", "ROUND_HALF_EVEN", "won", 50, 12, 5, 3} & (
        constants)
    assert not [node for node in ast.walk(tree) if isinstance(node, ast.Call)
                and getattr(node.func, "id", None) == "Decimal"], "no quantum is built here"


def test_the_three_concentration_constants_are_read_by_the_digest_and_by_concentration_alone():
    """
    OD-2: defined at M2 and consumed at M3. At M2 their only reader was the
    digest. From M3 concentration reads them as well, each in the module
    that defines it, and nothing else does: the quantum where a share is
    rounded, three times, and the two counts where the holders are taken.
    None is redefined (test_each_constant_is_defined_once_and_never_restated).
    """
    readers = {}
    for name in ("SHARE_QUANTUM", "CONCENTRATION_TOP_N", "CUMULATIVE_POINTS"):
        readers[name] = sorted(
            path.relative_to(REPO).as_posix()
            for path in (REPO / "app").rglob("*.py")
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
            if isinstance(node, ast.Name) and node.id == name and isinstance(node.ctx, ast.Load))

    assert readers == {
        "SHARE_QUANTUM": ["app/pipeline/config.py", *["app/pipeline/measures.py"] * 3],
        "CONCENTRATION_TOP_N": ["app/pipeline/aggregation.py", "app/pipeline/config.py"],
        "CUMULATIVE_POINTS": ["app/pipeline/aggregation.py", "app/pipeline/config.py"],
    }


# ---------------------------------------------------------------------------
# The methodology digest (plan A22.3 item 3, OD-1; C-18)
# ---------------------------------------------------------------------------


def test_the_canonical_text_written_here_is_the_plans_line():
    """
    What plan 0.12 measured of the line: 235 characters, 235 bytes, all
    ASCII, no whitespace, forty U+0022 quotation marks, nine lowercase keys
    in ascending code-point order, every value a string or a list of strings.
    """
    text = CANONICAL_METHODOLOGY_1

    assert len(text) == len(text.encode("utf-8")) == 235 and text.isascii()
    assert not re.search(r"\s", text) and text.count('"') == 40
    assert text.startswith("{") and text.endswith("}")
    parsed = yaml.safe_load(text)
    assert list(parsed) == METHODOLOGY_KEYS == sorted(METHODOLOGY_KEYS)
    assert all(key == key.lower() for key in parsed)
    assert parsed == {
        "arithmetic_precision": "50", "base_quantum": "0.01", "closed_stages": ["won"],
        "concentration_top_n": "5", "cumulative_points": ["1", "3", "5"], "period_horizon": "12",
        "rounding": "ROUND_HALF_EVEN", "share_quantum": "0.0001", "weight_quantum": "0.01"}


def test_the_canonical_text_of_the_committed_rules_is_the_plans_line_character_for_character(
        committed):
    """C-18. Compared as text: two implementations written from the plan give this line."""
    assert committed.methodology_text == CANONICAL_METHODOLOGY_1


def test_the_digest_is_the_sha256_of_the_canonical_texts_utf_8_bytes(committed):
    """Against the line written out above, so the formula is proved and not restated."""
    assert hashlib.sha256(CANONICAL_METHODOLOGY_1.encode("utf-8")).hexdigest() == PIN
    assert committed.methodology_digest == PIN
    assert re.fullmatch(r"[0-9a-f]{64}", committed.methodology_digest)


def test_the_committed_rules_are_pinned_by_their_pipeline_version(fresh_default):
    """Plan A22.3 item 4: the committed version is a key, and its digest is the pinned value."""
    current = default_pipeline_rules()

    assert current.pipeline_version in PINNED_METHODOLOGIES
    assert current.methodology_digest == PINNED_METHODOLOGIES[current.pipeline_version]


def test_the_pin_is_a_literal_and_not_the_implementations_own_output():
    """A pin read back from the code it pins would pin nothing."""
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    (pin,) = [node.value for node in tree.body if isinstance(node, ast.Assign)
              and [getattr(target, "id", None) for target in node.targets]
              == ["PINNED_METHODOLOGIES"]]

    assert isinstance(pin, ast.Dict)
    assert all(isinstance(node, ast.Constant) for node in [*pin.keys, *pin.values])
    assert ast.literal_eval(pin) == PINNED_METHODOLOGIES
    assert all(type(version) is int and re.fullmatch(r"[0-9a-f]{64}", digest)
               for version, digest in PINNED_METHODOLOGIES.items())


def test_the_pipeline_version_is_the_key_of_a_pin_and_is_not_inside_the_digest(tmp_path):
    """Plan A22.3 item 3, "the version": two versions may share a digest."""
    second = load_with(tmp_path, pipeline_version=2)

    assert second.pipeline_version == 2
    assert second.methodology_text == CANONICAL_METHODOLOGY_1
    assert second.methodology_digest == PIN
    assert "pipeline_version" not in second.methodology_text
    assert '"version"' not in second.methodology_text


#: One constant changed at a time, as the digest's module sees it, with the
#: canonical text the change must give. Each differs from the plan's line in
#: exactly that constant's value.
CHANGED_CONSTANTS = [
    ("ARITHMETIC_PRECISION", 28, '"arithmetic_precision":"50"', '"arithmetic_precision":"28"'),
    ("BASE_QUANTUM", Decimal("0.001"), '"base_quantum":"0.01"', '"base_quantum":"0.001"'),
    ("CONCENTRATION_TOP_N", 10, '"concentration_top_n":"5"', '"concentration_top_n":"10"'),
    ("CUMULATIVE_POINTS", (1, 3, 10), '"cumulative_points":["1","3","5"]',
     '"cumulative_points":["1","3","10"]'),
    ("PERIOD_HORIZON", 6, '"period_horizon":"12"', '"period_horizon":"6"'),
    ("ROUNDING_MODE", ROUND_HALF_UP, '"rounding":"ROUND_HALF_EVEN"', '"rounding":"ROUND_HALF_UP"'),
    ("SHARE_QUANTUM", Decimal("0.01"), '"share_quantum":"0.0001"', '"share_quantum":"0.01"'),
    ("WEIGHT_QUANTUM", Decimal("1"), '"weight_quantum":"0.01"', '"weight_quantum":"1"'),
]


@pytest.mark.parametrize(("name", "value", "old", "new"), CHANGED_CONSTANTS,
                         ids=[name for name, *_ in CHANGED_CONSTANTS])
def test_changing_any_one_of_the_eight_constants_changes_the_digest(
        committed, monkeypatch, name, value, old, new):
    """C-18: the digest is computed from the constant, so no change to one goes unseen."""
    assert CANONICAL_METHODOLOGY_1.count(old) == 1
    expected = CANONICAL_METHODOLOGY_1.replace(old, new)

    monkeypatch.setattr(config_module, name, value)

    assert committed.methodology_text == expected
    assert committed.methodology_digest == hashlib.sha256(expected.encode("utf-8")).hexdigest()
    assert committed.methodology_digest != PIN


def test_the_eight_changes_cover_the_eight_constants():
    assert sorted(name for name, *_ in CHANGED_CONSTANTS) == sorted(CONSTANTS)


#: The SHA-256 of the plan's line with ["won"] replaced by ["negotiation","won"],
#: derived outside the application with `shasum`.
CHANGED_STAGES_DIGEST = "2d42c15c0928721e1545159c5bba938a2751bcc76cae17f37696300442d1a30e"


def test_changing_the_closed_stages_changes_the_digest(tmp_path):
    """C-18: on the committed file's values, one closed stage added, the version left alone."""
    changed = load_with(tmp_path, closed_stages=["won", "negotiation"])
    expected = CANONICAL_METHODOLOGY_1.replace('["won"]', '["negotiation","won"]')

    assert changed.pipeline_version == 1
    assert changed.methodology_text == expected
    assert changed.methodology_digest == hashlib.sha256(expected.encode("utf-8")).hexdigest()
    assert changed.methodology_digest == CHANGED_STAGES_DIGEST
    assert changed.methodology_digest != PINNED_METHODOLOGIES[changed.pipeline_version]


@pytest.mark.parametrize("written", [
    ["won", "negotiation", "qualification"], ["qualification", "won", "negotiation"],
    ["negotiation", "won", "qualification", "won", "negotiation"]])
def test_the_closed_stages_are_hashed_as_their_distinct_values_ascending(tmp_path, written):
    """Plan A22.3 item 3: the file's order and a value written twice change nothing."""
    assert '"closed_stages":["negotiation","qualification","won"]' in (
        load_with(tmp_path, closed_stages=written).methodology_text)


_ORDER_PROBE = """
import sys
from app.pipeline.config import PipelineConfigError, load_pipeline_rules

stages = frozenset({"negotiation", "qualification", "won"})
missing = frozenset({"version", "pipeline_version", "closed_stages"}) - {"zeta", "alpha"}
unknown = {"zeta", "alpha", "beta"} - frozenset({"version", "pipeline_version", "closed_stages"})
print("ascending as iterated:", list(stages) == sorted(stages),
      list(missing) == sorted(missing), list(unknown) == sorted(unknown))
print(load_pipeline_rules(sys.argv[1]).methodology_text)
try:
    load_pipeline_rules(sys.argv[2])
except PipelineConfigError as refused:
    print(str(refused).replace(sys.argv[2], "<file>"))
"""


@pytest.mark.parametrize("hash_seed", ["0", "1"])
def test_no_order_the_rules_state_is_the_order_a_set_happens_to_iterate_in(tmp_path, hash_seed):
    """
    In a fresh process under a fixed hash seed. The first line is the
    control: under this seed a set of the three stages, and of a file's keys,
    does not iterate in ascending order. The closed stages are hashed
    ascending all the same, and a refusal names its keys ascending, so
    neither depends on the hash seed of the process that computes it.
    """
    every_stage = tmp_path / "every-stage.yaml"
    every_stage.write_text(yaml.safe_dump(
        {**VALID, "closed_stages": ["won", "qualification", "negotiation"]}), encoding="utf-8")
    other_keys = tmp_path / "other.yaml"
    other_keys.write_text(yaml.safe_dump({"zeta": 1, "alpha": 2, "beta": 3}), encoding="utf-8")

    completed = subprocess.run(
        [sys.executable, "-c", _ORDER_PROBE, str(every_stage), str(other_keys)], cwd=tmp_path,
        capture_output=True, text=True, check=True, timeout=120,
        env={**os.environ, "PYTHONPATH": str(REPO), "PYTHONDONTWRITEBYTECODE": "1",
             "PYTHONHASHSEED": hash_seed})

    assert completed.stdout.splitlines() == [
        "ascending as iterated: False False False",
        CANONICAL_METHODOLOGY_1.replace('["won"]', '["negotiation","qualification","won"]'),
        "<file>: missing keys ['closed_stages', 'pipeline_version', 'version'], "
        "unknown keys ['alpha', 'beta', 'zeta']",
    ]


def test_the_cumulative_points_are_hashed_in_the_constants_own_order(committed, monkeypatch):
    """Plan A22.3 item 3: not re-sorted. The order of the points is part of the methodology."""
    monkeypatch.setattr(config_module, "CUMULATIVE_POINTS", (5, 1, 3))

    assert '"cumulative_points":["5","1","3"]' in committed.methodology_text


def test_every_value_of_the_methodology_is_a_string_or_a_list_of_strings(committed):
    """Plan A22.3 item 3: no JSON number, boolean, null or nested object."""
    methodology = yaml.safe_load(committed.methodology_text)

    assert list(methodology) == METHODOLOGY_KEYS
    for value in methodology.values():
        assert type(value) is str or (
            type(value) is list and all(type(item) is str for item in value))
    assert not re.search(r'[:\[,](?:\d|true|false|null|\{)', committed.methodology_text)


@pytest.mark.parametrize("ambient", AMBIENT, ids=AMBIENT_IDS)
def test_the_digest_does_not_depend_on_the_callers_decimal_context(committed, ambient):
    """
    C-18: the digest is unchanged under an altered Decimal context. In the
    narrow ones VS-01's decimal_text alone would write a quantum as 0, or
    raise, so the context the digest states for itself is what holds.
    """
    with localcontext(ambient):
        assert committed.methodology_text == CANONICAL_METHODOLOGY_1
        assert committed.methodology_digest == PIN


def test_the_narrow_contexts_would_change_the_text_without_a_context_of_the_digests_own():
    """The control for the test above: it is not vacuous."""
    from app.intelligence.contract import decimal_text

    with localcontext(AMBIENT[2]):
        assert (decimal_text(SHARE_QUANTUM), decimal_text(WEIGHT_QUANTUM)) == ("0.1", "0.1")
    with localcontext(AMBIENT[3]):
        assert (decimal_text(SHARE_QUANTUM), decimal_text(WEIGHT_QUANTUM)) == ("0", "0.01")
    with localcontext(AMBIENT[4]), pytest.raises(decimal.DecimalException):
        decimal_text(SHARE_QUANTUM)
    assert (decimal_text(SHARE_QUANTUM), decimal_text(WEIGHT_QUANTUM)) == ("0.0001", "0.01")


@pytest.mark.parametrize("changes", SABOTAGE, ids=[str(changes) for changes in SABOTAGE])
def test_the_process_default_context_cannot_change_or_refuse_the_digest(committed, changes):
    """Every field the digest's context does not state is one the result does not depend on."""
    with process_default(**changes):
        assert committed.methodology_text == CANONICAL_METHODOLOGY_1
        assert committed.methodology_digest == PIN


def test_a_quantum_of_any_length_is_hashed_exactly(committed, monkeypatch):
    """The digest's precision comes from the quantum itself, so no digit of one is ever lost."""
    long = "0.0123456789012345678901234567890123456789012345678901234567890123456789"
    monkeypatch.setattr(config_module, "WEIGHT_QUANTUM", Decimal(long))
    monkeypatch.setattr(config_module, "BASE_QUANTUM", Decimal("0.0100"))
    monkeypatch.setattr(config_module, "SHARE_QUANTUM", Decimal("0"))

    with localcontext(Context(prec=3, rounding=ROUND_UP)):
        text = committed.methodology_text

    assert f'"weight_quantum":"{long}"' in text
    assert '"base_quantum":"0.01"' in text, "VS-01's decimal_text drops trailing zeros"
    assert '"share_quantum":"0"' in text


def test_the_serialisers_are_vs01s_imported_and_not_copied():
    """Plan A22.3 item 3: one convention, the one A7.4 and A14.10 use."""
    from app.intelligence import contract

    assert config_module.canonical_json is contract.canonical_json
    assert config_module.decimal_text is contract.decimal_text


def test_equal_rules_are_equal_and_share_a_digest(tmp_path, committed):
    same = load_with(tmp_path)

    assert same == committed and same is not committed and hash(same) == hash(committed)
    assert same.methodology_digest == committed.methodology_digest


# ---------------------------------------------------------------------------
# Lazy loading (plan A7.3 item 3, A22.5 seam 1)
# ---------------------------------------------------------------------------

_PROBE = """
import sys
opened = []
def hook(event, args):
    if event == "open" and str(args[0]).endswith("pipeline_rules.yaml"):
        opened.append(str(args[0]))
sys.addaudithook(hook)

import app.main
print("startup", len(opened), "app.pipeline" in sys.modules, "app.fx" in sys.modules)

import app.pipeline
from app.pipeline.config import default_pipeline_rules, load_pipeline_rules
print("import", len(opened))

other = load_pipeline_rules(sys.argv[1])
print("path", len(opened), other.pipeline_version, sorted(other.closed_stages))

first = default_pipeline_rules()
print("first use", opened)
kept = all(default_pipeline_rules() is first for _ in range(3))
print("later use", len(opened), kept)
print("committed", first.pipeline_version, first.methodology_digest)
"""


@pytest.mark.parametrize("hash_seed", ["0", "4242"])
def test_the_rules_file_is_read_on_first_use_and_never_at_import_or_startup(tmp_path, hash_seed):
    """
    In a fresh process, from another working directory, under two hash seeds:
    starting the application imports neither VS-02 package and reads nothing;
    importing the package reads nothing; a file loaded by path never touches
    the committed one; the first use of the default reads it once, from the
    repository; later uses read nothing. The digest is the pinned one
    whatever the hash seed.
    """
    other = candidate(tmp_path, pipeline_version=7, closed_stages=["won", "negotiation"])

    completed = subprocess.run(
        [sys.executable, "-c", _PROBE, str(other)], cwd=tmp_path, capture_output=True, text=True,
        check=True, timeout=120,
        env={**os.environ, "PYTHONPATH": str(REPO), "PYTHONDONTWRITEBYTECODE": "1",
             "PYTHONHASHSEED": hash_seed})

    assert completed.stdout.splitlines() == [
        "startup 0 False False",
        "import 0",
        "path 0 7 ['negotiation', 'won']",
        f"first use {[str(REPO / 'config' / 'intelligence' / 'pipeline_rules.yaml')]}",
        "later use 1 True",
        f"committed 1 {PIN}",
    ]


def test_the_default_rules_are_loaded_once_and_kept_for_the_process(fresh_default, committed):
    first = default_pipeline_rules()

    assert default_pipeline_rules() is first
    assert first == committed and first is not committed
    assert default_pipeline_rules.cache_info().misses == 1


def test_a_failed_load_is_not_kept_and_a_successful_one_is(tmp_path, monkeypatch, fresh_default):
    """A refused file fails every call until it is corrected; then the rules are kept as loaded."""
    path = candidate(tmp_path, closed_stages=["lost"])
    monkeypatch.setattr(config_module, "DEFAULT_PIPELINE_RULES_PATH", path)

    for _ in range(2):
        with pytest.raises(PipelineConfigError, match="'lost' is not a Layer 1 stage value"):
            default_pipeline_rules()
    assert default_pipeline_rules.cache_info().currsize == 0

    candidate(tmp_path)
    corrected = default_pipeline_rules()
    assert corrected.methodology_digest == PIN

    candidate(tmp_path, pipeline_version=2)
    assert default_pipeline_rules() is corrected
    assert default_pipeline_rules().pipeline_version == 1


def test_the_path_loader_reads_its_file_every_time_and_never_fills_the_default(
        tmp_path, fresh_default):
    """Plan A22.5: a test authors a file of its own and loads it through the path loader."""
    first = load_with(tmp_path, pipeline_version=2)
    second = load_with(tmp_path, pipeline_version=3)

    assert (first.pipeline_version, second.pipeline_version) == (2, 3)
    assert default_pipeline_rules.cache_info().currsize == 0
    assert default_pipeline_rules().pipeline_version == 1


# ---------------------------------------------------------------------------
# Loader refusals: the file
# ---------------------------------------------------------------------------


def test_a_missing_file_is_named_rather_than_defaulted(tmp_path):
    """There are no built-in rules to fall back on."""
    assert refusal(tmp_path / "absent.yaml") == f"Pipeline rules file not found: {FILE}"


def test_a_directory_is_not_a_rules_file(tmp_path):
    assert refusal(tmp_path) == f"Pipeline rules file not found: {FILE}"


def test_the_loader_takes_a_path_or_its_text(tmp_path):
    path = candidate(tmp_path)

    assert load_pipeline_rules(str(path)) == load_pipeline_rules(path)


def test_invalid_yaml_is_reported_with_its_location(tmp_path):
    message = refusal(write_text(tmp_path, "version: 1\n  closed_stages: [\n"))

    assert message.startswith(f"{FILE}: invalid YAML: ")


def test_a_file_holds_exactly_one_document(tmp_path):
    text = yaml.safe_dump(VALID)

    assert refusal(write_text(tmp_path, f"{text}---\n{text}")).startswith(
        f"{FILE}: invalid YAML: expected a single document")


def test_a_python_object_tag_is_refused_and_constructs_nothing(tmp_path):
    """yaml.safe_load only (plan A7.3 item 1): a tag that would run code is a broken file."""
    message = refusal(write_text(
        tmp_path, "version: 1\npipeline_version: 1\n"
                  "closed_stages: !!python/object/apply:os.system ['true']\n"))

    assert message.startswith(f"{FILE}: invalid YAML: could not determine a constructor")


def test_a_file_that_is_not_utf_8_is_refused_as_a_broken_file(tmp_path):
    path = tmp_path / "candidate.yaml"
    path.write_bytes("version: 1\npipeline_version: 1\nclosed_stages: [won]  # \xe9\n".encode(
        "latin-1"))

    assert refusal(path).startswith(f"{FILE}: invalid YAML: 'utf-8' codec can't decode")


@pytest.mark.parametrize("text", ["", "- version\n- pipeline_version\n", "won\n", "1\n",
                                  "null\n"])
def test_a_file_that_is_not_a_mapping_is_refused(tmp_path, text):
    assert refusal(write_text(tmp_path, text)) == f"{FILE}: expected a mapping"


@pytest.mark.parametrize("key", sorted(VALID))
def test_a_missing_key_is_named(tmp_path, key):
    partial = {name: value for name, value in VALID.items() if name != key}

    assert refusal(write(tmp_path, partial)) == (
        f"{FILE}: missing keys ['{key}'], unknown keys []")


@pytest.mark.parametrize("key", ["rate_set_version", "base_currency", "open_stages",
                                 "period_horizon", "weight_quantum", "rounding", "digest", 7])
def test_an_unknown_key_is_refused_by_name(tmp_path, key):
    """Plan A22.3 items 1 and 2: every other parameter is a constant in code, not a key here."""
    assert refusal(write(tmp_path, {**VALID, key: 1})) == (
        f"{FILE}: missing keys [], unknown keys ['{key}']")


def test_a_refusal_names_keys_in_one_order_whatever_the_files_order(tmp_path):
    assert refusal(write(tmp_path, {"zeta": 1, "version": 1, "alpha": 2})) == (
        f"{FILE}: missing keys ['closed_stages', 'pipeline_version'], "
        "unknown keys ['alpha', 'zeta']")


@pytest.mark.parametrize("version", [2, 0, -1, True, 1.0, "1", None])
def test_an_unsupported_file_format_is_refused(tmp_path, version):
    assert refusal(candidate(tmp_path, version=version)) == (
        f"{FILE}: unsupported version {version!r}")


# ---------------------------------------------------------------------------
# Loader refusals: the two values
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("pipeline_version", [0, -1, True, False, 1.0, 1.5, "1", None, [1]])
def test_the_pipeline_version_must_be_an_integer_of_at_least_1(tmp_path, pipeline_version):
    """A boolean is not the integer 1, and a float is not a version."""
    assert refusal(candidate(tmp_path, pipeline_version=pipeline_version)) == VERSION_REFUSED


@pytest.mark.parametrize("pipeline_version", [1, 2, 10, 2 ** 40])
def test_a_pipeline_version_of_at_least_1_is_kept_as_written(tmp_path, pipeline_version):
    assert load_with(tmp_path, pipeline_version=pipeline_version).pipeline_version == (
        pipeline_version)


@pytest.mark.parametrize("closed_stages", [[], "won", {"won": True}, None, 5, True])
def test_the_closed_stages_must_be_a_non_empty_list(tmp_path, closed_stages):
    """Where the plan is silent: no list, or an empty one, is a broken file and not "none closed"."""
    assert refusal(candidate(tmp_path, closed_stages=closed_stages)) == STAGES_REFUSED


@pytest.mark.parametrize(("closed_stages", "index", "shown"), [
    (["lost"], 0, "'lost'"),
    (["won", "Won"], 1, "'Won'"),
    (["won", " won"], 1, "' won'"),
    (["won", ""], 1, "''"),
    (["won", "UNSTAGED"], 1, "'UNSTAGED'"),
    (["won", "ALL"], 1, "'ALL'"),
    ([1], 0, "1"),
    ([True], 0, "True"),
    ([None], 0, "None"),
    ([["won"]], 0, "['won']"),
    (["negotiation", {"won": 1}], 1, "{'won': 1}"),
])
def test_each_closed_stage_must_be_a_layer_1_stage_value(tmp_path, closed_stages, index, shown):
    """Plan A22.3: the vocabulary is the frozen D1 one. It is compared exactly and never widened."""
    assert refusal(candidate(tmp_path, closed_stages=closed_stages)) == (
        f"{FILE}: closed_stages[{index}]: {shown} is not a Layer 1 stage value")


def test_any_layer_1_stage_may_be_a_closed_stage_and_one_written_twice_is_one(tmp_path):
    stages = sorted(default_config().fields["deals"]["stage"].enum_values)

    assert stages == ["negotiation", "qualification", "won"]
    for stage in stages:
        assert load_with(tmp_path, closed_stages=[stage]).closed_stages == frozenset({stage})
    assert load_with(tmp_path, closed_stages=stages).closed_stages == frozenset(stages)
    assert load_with(tmp_path, closed_stages=["won", "won"]) == load_with(tmp_path)


def test_one_bad_value_refuses_the_whole_file(tmp_path):
    """No partial rules: the version is refused before a stage is looked at, and nothing loads."""
    assert refusal(candidate(tmp_path, pipeline_version=0, closed_stages=["lost"])) == (
        VERSION_REFUSED)
    assert refusal(candidate(tmp_path, version=2, pipeline_version=0)) == (
        f"{FILE}: unsupported version 2")
