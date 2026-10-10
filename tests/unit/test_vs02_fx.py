"""
VS02-M1 FX foundation: the rate set, its digest and pin, and conversion.

Every base-currency figure VS-02 will state is computed from one rate set,
and that rate set is a stated assumption a human authored. These tests pin
what was authored, refuse every file that is not exactly a rate set, and
check conversion against values worked out by hand.

Nothing here is proved through the code it is about. Every digest is the
SHA-256 of a canonical string written out in this file, or a literal
computed outside the application with hashlib and json alone. Every
converted amount is a literal compared as text, because Decimal("85") equals
Decimal("85.00") and equality would hide a missing quantize. Every refusal
is compared on its whole message with the file's own path removed, because a
path can spell a key by accident.

Where the plan is silent on a file's form, the loader refuses rather than
interprets, and the test says which rule it is pinning.
"""

from __future__ import annotations

import ast
import dataclasses
import decimal
import hashlib
import os
import re
import subprocess
import sys
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import date, datetime
from decimal import (
    ROUND_CEILING,
    ROUND_DOWN,
    ROUND_HALF_EVEN,
    ROUND_UP,
    Context,
    Decimal,
    Inexact,
    Rounded,
    getcontext,
    localcontext,
)
from pathlib import Path
from types import MappingProxyType

import pytest
import yaml

import app.fx
from app.fx import rates as rates_module
from app.fx.convert import (
    ARITHMETIC_PRECISION,
    BASE_QUANTUM,
    ROUNDING_MODE,
    arithmetic_context,
    convert,
)
from app.fx.errors import FxConfigError, FxError, FxRateMissingError
from app.fx.rates import DEFAULT_RATE_SET_PATH, RateSet, default_rate_set, load_rate_set
from app.intelligence.errors import ContractViolationError, CurrencyMismatchError
from app.intelligence.money import MoneyValue
from app.normalization.config import default_config

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[2]

#: Plan A7.4: rate_set_version -> digest. An entry is NEVER edited or removed;
#: a new rate_set_version adds an entry. An edit to the committed rate set
#: without a new version therefore fails the build here.
PINNED_RATE_SETS = {
    "1": "61313648d0ddfc69d8f5b0b40ea07fc90ecf35460c8a04a37e4f38e3d1588426",
}
PIN = PINNED_RATE_SETS["1"]

#: U-1: the owner's words, recorded at VS02-M0. Never reworded.
OWNER_NOTE = ("Owner-authored illustrative rates for VS-02 deterministic demo calculations and "
              "acceptance testing; not sourced from a live market feed.")

#: Plan A7.4's canonical JSON for rate set "1", written out by hand: keys
#: sorted, compact separators, the date as ISO text, and the rates as
#: [currency, decimal text] pairs ascending by currency.
CANONICAL_RATE_SET_1 = (
    '{"as_of_date":"2026-10-01","base_currency":"INR","rate_set_version":"1",'
    '"rates":[["EUR","100"],["INR","1"],["USD","85"]],'
    '"source_note":"' + OWNER_NOTE + '"}'
)

#: The committed file as plain values, written out here and never read back
#: through app.fx. yaml.safe_dump writes a str rate quoted, an int rate bare
#: and a float rate as a YAML float: the distinction the loader is tested on.
VALID = {
    "version": 1,
    "rate_set_version": "1",
    "base_currency": "INR",
    "as_of_date": date(2026, 10, 1),
    "source_note": OWNER_NOTE,
    "rates": {"INR": "1", "USD": "85", "EUR": "100"},
}

#: A rate set at the bounds of plan A7.2: a rate of 10 integer digits and 8
#: decimal places, and the smallest rate there is. Its canonical JSON is
#: written out by hand, as rate set "1"'s is.
WIDE = {"rate_set_version": "7", "source_note": "wide rates", "rates": {
    "INR": "1", "USD": "9999999979.49999999", "EUR": "0.00000001", "GBP": "83.2575"}}
CANONICAL_WIDE = (
    '{"as_of_date":"2026-10-01","base_currency":"INR","rate_set_version":"7",'
    '"rates":[["EUR","0.00000001"],["GBP","83.2575"],["INR","1"],'
    '["USD","9999999979.49999999"]],"source_note":"wide rates"}'
)
WIDE_DIGEST = hashlib.sha256(CANONICAL_WIDE.encode("utf-8")).hexdigest()

#: What a process could have done to decimal's own default context, from
#: which a Context(...) call takes every field it does not state.
SABOTAGE = [
    {"prec": 2, "rounding": ROUND_UP},
    {"Emax": 3},
    {"Emax": 3, "traps": False},
    {"traps": True},
    {"Emin": 0, "clamp": 1},
]

FILE = "<file>"
VERSION_REFUSED = f"{FILE}: rate_set_version: expected a non-empty string of at most 50 characters"
NOTE_REFUSED = f"{FILE}: source_note: expected a non-empty string of at most 500 characters"
NOTE_BROKEN = f"{FILE}: source_note: expected a single line, with no line break"
DATE_REFUSED = f"{FILE}: as_of_date: expected a YYYY-MM-DD date"
RATES_REFUSED = f"{FILE}: rates: expected a non-empty mapping"
NOT_POSITIVE = f"{FILE}: rates.USD: expected a positive rate"
TOO_PRECISE = f"{FILE}: rates.USD: more than 8 decimal places"
TOO_LARGE = f"{FILE}: rates.USD: more than 10 integer digits"
BASE_NOT_ONE = f"{FILE}: rates.INR: the base currency's rate must be exactly 1"


def not_a_rate(kind: str, currency: str = "USD") -> str:
    return (f"{FILE}: rates.{currency}: expected a rate written as a string or an integer, "
            f"not {kind}")


def write_text(tmp_path: Path, text: str) -> Path:
    """One candidate file, under a name that spells no key of a rate set."""
    path = tmp_path / "candidate.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def write(tmp_path: Path, data: object) -> Path:
    """Write values in the order given. Non-ASCII is escaped, so YAML cannot fold it away."""
    text = yaml.safe_dump(data, sort_keys=False)
    assert yaml.safe_load(text) == data, "the fixture must reach the loader as it was written"
    return write_text(tmp_path, text)


def candidate(tmp_path: Path, **overrides) -> Path:
    return write(tmp_path, {**VALID, **overrides})


def edited(tmp_path: Path, old: str, new: str) -> Path:
    """A copy of the committed file with exactly one change, where the lexical form is the input."""
    text = DEFAULT_RATE_SET_PATH.read_text(encoding="utf-8")
    assert text.count(old) == 1, f"{old!r} occurs {text.count(old)} times in the committed file"
    return write_text(tmp_path, text.replace(old, new))


def load_with(tmp_path: Path, **overrides) -> RateSet:
    return load_rate_set(candidate(tmp_path, **overrides))


def with_rates(tmp_path: Path, **rates) -> RateSet:
    return load_with(tmp_path, rates={"INR": "1", **rates})


def refusal(path: Path) -> str:
    """Why a file is refused: the whole message, with the file's own path replaced."""
    with pytest.raises(FxConfigError) as refused:
        load_rate_set(path)
    assert not isinstance(refused.value, FxError), "a refused file is not a conversion failure"
    assert str(path) in str(refused.value), "a refusal names the file it refuses"
    return str(refused.value).replace(str(path), FILE)


def converted(amount: str, currency: str, rate_set: RateSet) -> str:
    """The converted amount as text, after checking it is a new MoneyValue in the base currency."""
    value = MoneyValue(Decimal(amount), currency)
    result = convert(value, rate_set)
    assert type(result) is MoneyValue and result is not value
    assert result.currency == rate_set.base_currency
    return str(result.amount)


def _process_default() -> tuple[object, ...]:
    default = decimal.DefaultContext
    return (default.prec, default.rounding, default.Emin, default.Emax, default.clamp,
            dict(default.traps))


@contextmanager
def process_default(**changes: object) -> Iterator[None]:
    """decimal.DefaultContext with some fields changed, and put back whatever happens."""
    default = decimal.DefaultContext
    prec, rounding, emin, emax, clamp, traps = _process_default()
    try:
        for name, value in changes.items():
            if name == "traps":
                for signal in traps:
                    default.traps[signal] = value
            else:
                setattr(default, name, value)
        yield
    finally:
        default.prec, default.rounding, default.clamp = prec, rounding, clamp
        default.Emin, default.Emax = emin, emax
        for signal, value in traps.items():
            default.traps[signal] = value


@pytest.fixture
def committed() -> RateSet:
    """The committed rate set, loaded from its file and not from the process cache."""
    return load_rate_set(DEFAULT_RATE_SET_PATH)


@pytest.fixture
def fresh_default():
    """default_rate_set() with an empty cache before the test and after it."""
    default_rate_set.cache_clear()
    yield
    default_rate_set.cache_clear()


# ---------------------------------------------------------------------------
# The committed rate set (plan A7.2, A7.3; U-1)
# ---------------------------------------------------------------------------


def test_the_committed_file_is_authored_exactly_as_the_plan_records_it():
    """Read without app.fx. Rates are written as strings, so none has been through a float."""
    authored = yaml.safe_load(DEFAULT_RATE_SET_PATH.read_text(encoding="utf-8"))

    assert authored == VALID
    assert list(authored) == ["version", "rate_set_version", "base_currency", "as_of_date",
                              "source_note", "rates"]
    assert list(authored["rates"]) == ["INR", "USD", "EUR"]
    assert type(authored["version"]) is int
    assert type(authored["as_of_date"]) is date
    assert {type(rate) for rate in authored["rates"].values()} == {str}


def test_the_committed_rate_set_is_the_owners_stated_assumption(committed):
    assert committed.rate_set_version == "1"
    assert committed.base_currency == "INR"
    assert committed.as_of_date == date(2026, 10, 1)
    assert committed.source_note == OWNER_NOTE
    assert len(OWNER_NOTE) == 136
    assert dict(committed.rates) == {
        "EUR": Decimal("100"), "INR": Decimal("1"), "USD": Decimal("85")}


def test_a_rate_set_holds_its_five_authored_fields_and_one_derived(committed):
    """Plan A7.2: exactly these, with the types it states. The file-format version is not one."""
    assert [field.name for field in dataclasses.fields(RateSet)] == [
        "rate_set_version", "base_currency", "as_of_date", "source_note", "rates"]
    assert {name for name in dir(committed)
            if not name.startswith("_") and not callable(getattr(committed, name))} == {
        "rate_set_version", "base_currency", "as_of_date", "source_note", "rates", "digest"}
    assert type(committed.rate_set_version) is str
    assert type(committed.as_of_date) is date
    assert isinstance(committed.rates, Mapping)
    assert {type(rate) for rate in committed.rates.values()} == {Decimal}
    assert type(committed.digest) is str


def test_the_rates_read_in_ascending_order_whatever_the_files_order(tmp_path, committed):
    reordered = load_with(tmp_path, rates={"USD": "85", "INR": "1", "EUR": "100"})

    assert list(VALID["rates"]) == ["INR", "USD", "EUR"], "the committed file is not ascending"
    assert list(committed.rates) == ["EUR", "INR", "USD"]
    assert list(reordered.rates) == ["EUR", "INR", "USD"]


def test_a_rate_set_cannot_be_changed_after_it_is_loaded(committed):
    with pytest.raises(dataclasses.FrozenInstanceError):
        committed.rate_set_version = "2"  # type: ignore[misc]
    with pytest.raises(TypeError, match="does not support item assignment"):
        committed.rates["GBP"] = Decimal("105")  # type: ignore[index]
    with pytest.raises(TypeError, match="does not support item deletion"):
        del committed.rates["USD"]  # type: ignore[attr-defined]

    assert dict(committed.rates) == {
        "EUR": Decimal("100"), "INR": Decimal("1"), "USD": Decimal("85")}
    assert committed.digest == PIN


def test_the_default_path_is_the_committed_file_where_the_image_copies_it():
    assert DEFAULT_RATE_SET_PATH == REPO / "config" / "intelligence" / "fx_rates.yaml"
    assert DEFAULT_RATE_SET_PATH.is_file()


def test_the_package_exports_exactly_its_public_api():
    """Plan A22.1's names and A22.3's rounding mode, each the object its own module defines."""
    assert app.fx.__all__ == sorted(app.fx.__all__)
    assert all(hasattr(app.fx, name) for name in app.fx.__all__)
    assert (app.fx.ARITHMETIC_PRECISION, app.fx.BASE_QUANTUM, app.fx.ROUNDING_MODE) == (
        ARITHMETIC_PRECISION, BASE_QUANTUM, ROUNDING_MODE)
    assert set(app.fx.__all__) == {
        "ARITHMETIC_PRECISION", "BASE_QUANTUM", "ROUNDING_MODE", "FxConfigError", "FxError",
        "FxRateMissingError", "RateSet", "arithmetic_context", "convert", "default_rate_set",
        "load_rate_set"}
    assert (app.fx.convert, app.fx.arithmetic_context) == (convert, arithmetic_context)
    assert (app.fx.RateSet, app.fx.default_rate_set, app.fx.load_rate_set) == (
        RateSet, default_rate_set, load_rate_set)
    assert (app.fx.FxError, app.fx.FxConfigError, app.fx.FxRateMissingError) == (
        FxError, FxConfigError, FxRateMissingError)
    assert convert.__module__ == "app.fx.convert"
    assert {error.__module__ for error in (FxError, FxConfigError, FxRateMissingError)} == {
        "app.fx.errors"}


# ---------------------------------------------------------------------------
# Identity and digest (plan A7.4)
# ---------------------------------------------------------------------------


def test_the_digest_is_the_sha256_of_the_canonical_json_of_every_authored_field(committed):
    """Against a string written out by hand, so the formula is proved and not restated."""
    assert hashlib.sha256(CANONICAL_RATE_SET_1.encode("utf-8")).hexdigest() == PIN
    assert committed.digest == PIN
    assert re.fullmatch(r"[0-9a-f]{64}", committed.digest)


def test_the_committed_rate_set_is_pinned_by_its_version(fresh_default):
    """Plan A7.4: the committed file's version is a key, and its digest is the pinned value."""
    current = default_rate_set()

    assert current.rate_set_version in PINNED_RATE_SETS
    assert current.digest == PINNED_RATE_SETS[current.rate_set_version]


def test_the_pin_is_a_literal_and_not_the_implementations_own_output():
    """A pin read back from the code it pins would pin nothing."""
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    (pin,) = [node.value for node in tree.body if isinstance(node, ast.Assign)
              and [getattr(target, "id", None) for target in node.targets] == ["PINNED_RATE_SETS"]]

    assert isinstance(pin, ast.Dict)
    assert all(isinstance(node, ast.Constant) and isinstance(node.value, str)
               for node in [*pin.keys, *pin.values])
    assert ast.literal_eval(pin) == PINNED_RATE_SETS
    assert all(re.fullmatch(r"[0-9a-f]{64}", digest) for digest in PINNED_RATE_SETS.values())


def test_an_edit_to_the_committed_file_without_a_new_version_breaks_the_pin(tmp_path):
    """On a copy of the real file: one rate changed, the version left alone."""
    changed = load_rate_set(edited(tmp_path, 'USD: "85"', 'USD: "86"'))

    assert changed.rate_set_version == "1"
    assert changed.digest == "1d406dfd3b0bd350341c85f144330bd164dba949e10dc776eedb688ca0cfbbff"
    assert changed.digest != PINNED_RATE_SETS[changed.rate_set_version]


@pytest.mark.parametrize(("change", "digest"), [
    ({"rate_set_version": "2"},
     "000f6214e0c7523c15480f9cd12ca4e462441637d5fc24905d50f05221a62cdc"),
    ({"rate_set_version": "v" * 50},
     "65f6fe1af0424d238562a30ef6984666ecf8aa05739b45392e5b832b049f492c"),
    ({"as_of_date": date(2026, 10, 2)},
     "6f617199e6e2ee16ebfb3c68e14bb326ab2355efa84d2e6a2f3562cfb33155cd"),
    ({"source_note": OWNER_NOTE[:-1]},
     "0c32946bcbe0673c47cc7f2f4832524841ebb7394d7f3221ae277f20f7981c14"),
    ({"rates": {"INR": "1", "USD": "86", "EUR": "100"}},
     "1d406dfd3b0bd350341c85f144330bd164dba949e10dc776eedb688ca0cfbbff"),
    ({"rates": {"INR": "1", "USD": "85", "EUR": "100.5"}},
     "cc10495c1c5e5543dcd5c55ad67c5c764847e771b4be6abf4a87bbbcb42a35c0"),
    ({"rates": {"INR": "1", "USD": "85", "EUR": "100", "GBP": "105"}},
     "4fabab52339a091ce96e5bf830a6329c418f99f9e579102c715eb00501340f62"),
    ({"rates": {"INR": "1", "USD": "85"}},
     "2e57e76de4c8cf6acc26487c20051a85fb4d0aafaaff26d83e11b14d56582c5d"),
    ({"rates": {"INR": "1"}},
     "7dcd10f50672f4733b2a33f1b40b1002135b47d2878fb8f06aea003793c78160"),
    ({"rates": {"INR": "1", "USD": "1", "EUR": "100"}},
     "ee5ec9944cbdda53fb08cbfc89b7c0d3828323204faa5398b368e8a3ee1a444f"),
    ({"base_currency": "USD", "rates": {"INR": "1", "USD": "1", "EUR": "100"}},
     "87e0fe4585fc98586c6001fdd6ddd400100748f4184374dabda957913e9b7633"),
], ids=["version", "longest-version", "date", "note", "usd-rate", "eur-rate", "added-rate",
        "removed-rate", "base-alone", "usd-at-par", "base-currency"])
def test_a_change_to_any_authored_field_gives_a_different_known_digest(tmp_path, change, digest):
    """
    Each digest was computed outside the application, with hashlib and json
    alone, so a digest that ignored a field or salted itself would not match.
    The last two differ in the base currency and in nothing else.
    """
    assert digest != PIN
    assert load_with(tmp_path, **change).digest == digest


def test_the_digest_does_not_depend_on_how_the_same_content_is_written(tmp_path):
    """Key order, rate order and the spelling of one number are not content."""
    reordered = {key: VALID[key] for key in reversed(list(VALID))}
    reordered["rates"] = {"EUR": "100", "USD": "85", "INR": "1"}

    assert load_rate_set(write(tmp_path, reordered)).digest == PIN
    assert load_rate_set(edited(tmp_path, 'USD: "85"', "USD: 85")).digest == PIN
    for usd in (85, "85.0", "85.00000000", "085"):
        assert with_rates(tmp_path, USD=usd, EUR="100").digest == PIN, usd
    for inr in (1, "1.0", "1.00000000"):
        assert load_with(tmp_path, rates={"INR": inr, "USD": "85", "EUR": "100"}).digest == PIN, inr


def test_a_rate_is_hashed_as_its_canonical_decimal_text(tmp_path):
    """0.50 is hashed as 0.5: VS-01's decimal_text, which the pinned 1, 85 and 100 cannot show."""
    half = "373468f660775189b109054cc6adf3f107d0715ca9e80918ed1612c75a97870f"

    assert with_rates(tmp_path, USD="0.50").digest == half
    assert with_rates(tmp_path, USD="0.5").digest == half


def test_the_note_is_hashed_as_utf_8_text_and_not_as_ascii_escapes(tmp_path):
    """canonical_json keeps non-ASCII text as itself, and the digest is of its UTF-8 bytes."""
    note = "Taux indicatif \N{EM DASH} 85 \N{INDIAN RUPEE SIGN} par USD"
    stated = load_with(tmp_path, source_note=note)

    assert stated.source_note == note
    assert stated.digest == "b91a415575f8b81e81aa586fc44a8f63d8658b76cbefb16882be9e59ba6065e2"


@pytest.mark.parametrize("ambient", [
    Context(prec=1), Context(prec=5, rounding=ROUND_UP), Context(prec=17),
    Context(prec=28, traps=[Inexact, Rounded]),
], ids=["prec-1", "prec-5-up", "prec-17", "traps"])
def test_the_digest_does_not_depend_on_the_callers_decimal_context(tmp_path, ambient):
    """
    VS-01's decimal_text normalizes in the current context: at five digits of
    precision it would write 9999999979.49999999 as 10000000000. The digest
    states its own context, so an identity never moves with the caller's.
    """
    wide = load_with(tmp_path, **WIDE)

    assert wide.digest == WIDE_DIGEST
    with localcontext(ambient):
        digest = wide.digest
        loaded_there = load_with(tmp_path, **WIDE)
        assert (getcontext().prec, getcontext().rounding) == (ambient.prec, ambient.rounding)
    assert digest == WIDE_DIGEST
    assert {code: format(rate, "f") for code, rate in loaded_there.rates.items()} == WIDE["rates"]
    assert loaded_there.digest == WIDE_DIGEST


@pytest.mark.parametrize("changes", SABOTAGE, ids=[
    "prec-2-up", "emax-3", "emax-3-no-traps", "every-trap", "emin-0-clamp"])
def test_the_process_default_context_cannot_change_or_refuse_a_digest_or_a_figure(
        tmp_path, committed, changes):
    """
    Plan A9.1: the process default context is never relied on. A Context(...)
    call takes every field it does not state from decimal.DefaultContext, so
    the code states each one that could alter a result or refuse it. With the
    exponent limit lowered and the traps cleared, an inherited limit would
    hash a rate as Infinity; with every signal trapped, it would refuse to
    round at all.
    """
    wide = load_with(tmp_path, **WIDE)
    before = _process_default()

    with process_default(**changes):
        assert _process_default() != before, "the sabotage must take hold"
        stated = arithmetic_context()
        digests = (committed.digest, wide.digest)
        figures = [converted("193373.46", "USD", committed), converted("0.001", "USD", committed),
                   converted("2.675", "INR", committed), converted("9999999999999.99", "USD", wide)]

    assert _process_default() == before
    assert (stated.prec, stated.rounding, stated.Emin, stated.Emax) == (
        50, ROUND_HALF_EVEN, decimal.MIN_EMIN, decimal.MAX_EMAX)
    assert {signal for signal, trapped in stated.traps.items() if trapped} == {
        decimal.InvalidOperation, decimal.DivisionByZero, decimal.Overflow}
    assert digests == (PIN, WIDE_DIGEST)
    assert figures == ["16436744.10", "0.08", "2.68", "99999999794999899900000.21"]


def test_the_digest_is_exact_for_a_rate_of_any_length():
    """
    The digest takes its precision from the rates themselves and not from
    the loader's bounds, so two rate sets that differ in any digit of any
    rate can never share an identity. Built by hand, because the loader
    refuses a rate this long.
    """
    def hand_built(usd: str) -> RateSet:
        return RateSet("1", "INR", date(2026, 10, 1), "n", MappingProxyType(
            {"INR": Decimal("1"), "USD": Decimal(usd)}))
    canonical = ('{"as_of_date":"2026-10-01","base_currency":"INR","rate_set_version":"1",'
                 '"rates":[["INR","1"],["USD","85.0000000000000000000000000001"]],'
                 '"source_note":"n"}')

    long = hand_built("85.0000000000000000000000000001")

    assert long.digest == hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    assert long.digest != hand_built("85").digest
    assert hand_built("85.00").digest == hand_built("85").digest


def test_the_digest_orders_the_rates_itself():
    """Plan A7.4: rates ascending by currency code. The digest does not lean on the loader's order."""
    unsorted = RateSet("1", "INR", date(2026, 10, 1), OWNER_NOTE, MappingProxyType(
        {"USD": Decimal("85"), "INR": Decimal("1"), "EUR": Decimal("100")}))

    assert list(unsorted.rates) == ["USD", "INR", "EUR"]
    assert unsorted.digest == PIN


def test_equal_rate_sets_are_equal_and_share_a_digest(tmp_path, committed):
    again = load_with(tmp_path)

    assert again == committed and again is not committed
    assert again.digest == committed.digest
    assert load_with(tmp_path, rate_set_version="2") != committed


# ---------------------------------------------------------------------------
# Lazy loading (plan A7.3 item 3, A19 item 7)
# ---------------------------------------------------------------------------


#: Run in a fresh interpreter, so no earlier import in this process can hide a
#: read. An audit hook sees every open() however it is made (Path.read_text,
#: open, io.open, os.open) and assumes nothing about how the default is cached.
_PROBE = """
import dataclasses, sys
opened = []
def hook(event, args):
    if event == "open" and str(args[0]).endswith("fx_rates.yaml"):
        opened.append(str(args[0]))
sys.addaudithook(hook)

from decimal import Decimal, getcontext
from app.intelligence.money import MoneyValue
before = {name: id(value) for name, value in vars(MoneyValue).items()}

import app.main
ambient = (getcontext().prec, getcontext().rounding, dict(getcontext().traps))
print("startup", len(opened))

import app.fx
from app.fx.convert import convert
from app.fx.errors import FxError
from app.fx.rates import default_rate_set, load_rate_set
print("import", len(opened))

other = load_rate_set(sys.argv[1])
amount = convert(MoneyValue(Decimal("2"), "USD"), other).amount
print("convert", len(opened), amount)
print("digest", other.digest)

first = default_rate_set()
print("first use", opened)
kept = all(default_rate_set() is first for _ in range(3))
print("later use", len(opened), kept)
print("committed", first.digest)
print("money", before == {name: id(value) for name, value in vars(MoneyValue).items()},
      [field.name for field in dataclasses.fields(MoneyValue)])
print("context", ambient == (getcontext().prec, getcontext().rounding, dict(getcontext().traps)))
"""


@pytest.mark.parametrize("hash_seed", ["0", "4242"])
def test_the_rate_file_is_read_on_first_use_and_never_at_import_or_startup(tmp_path, hash_seed):
    """
    In a fresh process, from another working directory, under two hash seeds:
    importing the application and the package reads nothing; converting with
    a rate set loaded by path never touches the committed file; the first use
    of the default reads it once, from the repository; later uses read nothing.
    MoneyValue is the same object before and after, both digests are the
    known ones whatever the hash seed, and the process's Decimal context is
    the one the application started with: importing the package, loading a
    rate set and converting an amount do not alter it.
    """
    eight = candidate(tmp_path, rates={"INR": "1", "USD": "85", "EUR": "100", "GBP": "105",
                                       "JPY": "0.55", "AED": "23.1", "CHF": "95.5", "SGD": "63"})

    completed = subprocess.run(
        [sys.executable, "-c", _PROBE, str(eight)], cwd=tmp_path, capture_output=True, text=True,
        check=True, timeout=120,
        env={**os.environ, "PYTHONPATH": str(REPO), "PYTHONDONTWRITEBYTECODE": "1",
             "PYTHONHASHSEED": hash_seed})

    assert completed.stdout.splitlines() == [
        "startup 0",
        "import 0",
        "convert 0 170.00",
        "digest 0c52f7c3dba2687067f101ab213d5f5e4f41e7c46ec180c32341fa13bd01ebb6",
        f"first use {[str(REPO / 'config' / 'intelligence' / 'fx_rates.yaml')]}",
        "later use 1 True",
        f"committed {PIN}",
        "money True ['amount', 'currency']",
        "context True",
    ]


def test_the_default_rate_set_is_loaded_once_and_kept_for_the_process(fresh_default, committed):
    first = default_rate_set()

    assert default_rate_set() is first
    assert first == committed and first is not committed
    assert default_rate_set.cache_info().misses == 1


def test_a_failed_load_is_not_kept_and_a_successful_one_is(tmp_path, monkeypatch, fresh_default):
    """A refused file fails every call until it is corrected; then the set is kept as loaded."""
    path = candidate(tmp_path, rates={"INR": "1", "USD": 85.5})
    monkeypatch.setattr(rates_module, "DEFAULT_RATE_SET_PATH", path)

    for _ in range(2):
        with pytest.raises(FxConfigError, match="not float"):
            default_rate_set()
    assert default_rate_set.cache_info().currsize == 0

    candidate(tmp_path)
    corrected = default_rate_set()
    assert corrected.digest == PIN

    candidate(tmp_path, rates={"INR": "1", "USD": "86", "EUR": "100"})
    assert default_rate_set() is corrected
    assert default_rate_set().rates["USD"] == Decimal("85")


def test_the_path_loader_reads_its_file_every_time_and_never_fills_the_default(
        tmp_path, fresh_default):
    """Plan A22.5: a test authors a file of its own and loads it through the path loader."""
    first = load_rate_set(candidate(tmp_path, rate_set_version="2"))
    second = load_rate_set(candidate(tmp_path, rate_set_version="3"))

    assert (first.rate_set_version, second.rate_set_version) == ("2", "3")
    assert default_rate_set.cache_info().currsize == 0
    assert default_rate_set().rate_set_version == "1"


# ---------------------------------------------------------------------------
# Loader refusals: the file (plan A7.3 item 1)
# ---------------------------------------------------------------------------


def test_a_missing_file_is_named_rather_than_defaulted(tmp_path):
    """There is no built-in rate set to fall back on (plan A7.6)."""
    assert refusal(tmp_path / "absent.yaml") == f"FX rate set file not found: {FILE}"


def test_a_directory_is_not_a_rate_file(tmp_path):
    assert refusal(tmp_path) == f"FX rate set file not found: {FILE}"


def test_the_loader_takes_a_path_or_its_text(tmp_path):
    path = candidate(tmp_path)

    assert load_rate_set(str(path)) == load_rate_set(path)


def test_invalid_yaml_is_reported_with_its_location(tmp_path):
    message = refusal(write_text(tmp_path, "version: 1\n  rates: [\n"))

    assert message.startswith(f"{FILE}: invalid YAML: ")


def test_a_file_holds_exactly_one_rate_set(tmp_path):
    """Two documents in one file are not a rate set and its successor."""
    text = DEFAULT_RATE_SET_PATH.read_text(encoding="utf-8")

    message = refusal(write_text(tmp_path, text + "---\n" + text))

    assert message.startswith(f"{FILE}: invalid YAML: expected a single document")


def test_a_python_object_tag_is_refused_and_constructs_nothing(tmp_path):
    """yaml.safe_load only: a tag that would call into Python is invalid YAML here."""
    message = refusal(edited(tmp_path, 'USD: "85"', "USD: !!python/object/apply:os.getcwd []"))

    assert message.startswith(f"{FILE}: invalid YAML: could not determine a constructor")


def test_a_date_that_cannot_exist_is_refused_as_a_broken_file(tmp_path):
    """PyYAML raises a bare ValueError for 2026-02-30, not a YAMLError; it must not escape."""
    message = refusal(edited(tmp_path, "as_of_date: 2026-10-01", "as_of_date: 2026-02-30"))

    assert message.startswith(f"{FILE}: invalid YAML: ")


def test_a_file_that_is_not_utf_8_is_refused_as_a_broken_file(tmp_path):
    path = tmp_path / "candidate.yaml"
    path.write_bytes(DEFAULT_RATE_SET_PATH.read_bytes().replace(b"illustrative", b"\xe9"))

    assert refusal(path).startswith(f"{FILE}: invalid YAML: 'utf-8' codec can't decode byte 0xe9")


@pytest.mark.parametrize("text", [
    "- version\n- 1\n", "just text\n", "42\n", "", "# nothing but a comment\n",
], ids=["list", "text", "number", "empty", "comment"])
def test_a_file_that_is_not_a_mapping_is_refused(tmp_path, text):
    assert refusal(write_text(tmp_path, text)) == f"{FILE}: expected a mapping"


@pytest.mark.parametrize("key", sorted(VALID))
def test_a_missing_key_is_named(tmp_path, key):
    data = {name: value for name, value in VALID.items() if name != key}

    assert refusal(write(tmp_path, data)) == f"{FILE}: missing keys ['{key}'], unknown keys []"


@pytest.mark.parametrize("key", ["digest", "default_rate", "spread", "provider", "fetched_at",
                                 "weights", 7])
def test_an_unknown_key_is_refused_by_name(tmp_path, key):
    """An authored digest is refused with the rest: the digest is derived, never stated."""
    assert refusal(write(tmp_path, {**VALID, key: "x"})) == (
        f"{FILE}: missing keys [], unknown keys ['{key}']")


def test_a_refusal_names_keys_in_one_order_whatever_the_files_order(tmp_path):
    forward = refusal(write(tmp_path, {**VALID, "zeta": 1, "alpha": 2}))
    reverse = refusal(write(tmp_path, {"alpha": 2, "zeta": 1, **VALID}))
    both = {name: value for name, value in VALID.items() if name not in {"rates", "as_of_date"}}

    assert forward == reverse == f"{FILE}: missing keys [], unknown keys ['alpha', 'zeta']"
    assert refusal(write(tmp_path, {**both, "spread": 1})) == (
        f"{FILE}: missing keys ['as_of_date', 'rates'], unknown keys ['spread']")
    many = {"version": 1, **dict.fromkeys(("zeta", "mu", "alpha", "omega", "beta", "kappa"), 1)}
    assert refusal(write(tmp_path, many)) == (
        f"{FILE}: missing keys ['as_of_date', 'base_currency', 'rate_set_version', 'rates', "
        "'source_note'], unknown keys ['alpha', 'beta', 'kappa', 'mu', 'omega', 'zeta']")


@pytest.mark.parametrize("version", [2, 0, -1, True, 1.0, "1", None])
def test_an_unsupported_file_format_is_refused(tmp_path, version):
    """Only the integer 1. The plan names the key; refusing true and 1.0 is M6's rule."""
    assert refusal(candidate(tmp_path, version=version)) == (
        f"{FILE}: unsupported version {version!r}")


# ---------------------------------------------------------------------------
# Loader refusals: the authored fields (plan A7.2)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("rate_set_version", [1, 1.0, True, None, ["1"], "", "   ", "v" * 51])
def test_the_rate_set_version_must_be_a_string_of_1_to_50_characters(tmp_path, rate_set_version):
    """A blank string is empty, by M1's rule for a non-empty text."""
    assert refusal(candidate(tmp_path, rate_set_version=rate_set_version)) == VERSION_REFUSED


def test_an_unquoted_version_is_a_yaml_integer_and_not_the_string_that_names_a_set(tmp_path):
    assert refusal(edited(tmp_path, 'rate_set_version: "1"', "rate_set_version: 1")) == (
        VERSION_REFUSED)


@pytest.mark.parametrize("rate_set_version", [
    "1", "2026-10", "v" * 50, "\N{LATIN SMALL LETTER E WITH ACUTE}" * 50])
def test_a_rate_set_version_within_its_bounds_is_kept_as_written(tmp_path, rate_set_version):
    assert load_with(tmp_path, rate_set_version=rate_set_version).rate_set_version == (
        rate_set_version)


@pytest.mark.parametrize("base_currency", [
    "XYZ", "inr", "INR ", "", "\N{INDIAN RUPEE SIGN}", 356, None, ["INR"]])
def test_the_base_currency_must_be_a_layer_1_currency_code(tmp_path, base_currency):
    """The D1 vocabulary is the vocabulary, exactly: the rule MoneyValue already applies."""
    assert refusal(candidate(tmp_path, base_currency=base_currency)) == (
        f"{FILE}: base_currency: {base_currency!r} is not a configured ISO 4217 code")


@pytest.mark.parametrize("as_of_date", [
    "2026-10-01", 20261001, None, datetime(2026, 10, 1, 10, 30), ["2026-10-01"]])
def test_the_as_of_date_must_be_a_calendar_date(tmp_path, as_of_date):
    assert refusal(candidate(tmp_path, as_of_date=as_of_date)) == DATE_REFUSED


@pytest.mark.parametrize("written", [
    "2026-10-01 10:30:00", "2026-10-01T10:30:00Z", '"2026-10-01"', "20261001"])
def test_a_timestamp_or_a_quoted_date_in_the_file_is_not_a_calendar_date(tmp_path, written):
    assert refusal(edited(tmp_path, "as_of_date: 2026-10-01", f"as_of_date: {written}")) == (
        DATE_REFUSED)


@pytest.mark.parametrize("stated", [date(1999, 12, 31), date(2026, 10, 1), date(2099, 1, 1)])
def test_the_as_of_date_is_reported_and_never_matched_against_anything(tmp_path, stated):
    """Plan A7.2 rule 4: any calendar date loads. There is no staleness rule and no clock."""
    loaded = load_with(tmp_path, as_of_date=stated).as_of_date

    assert loaded == stated and type(loaded) is date


@pytest.mark.parametrize("source_note", ["", "   ", "\n", "n" * 501, None, 5, True, ["note"]])
def test_the_source_note_must_be_a_string_of_1_to_500_characters(tmp_path, source_note):
    """A blank note says nothing about where the assumption comes from."""
    assert refusal(candidate(tmp_path, source_note=source_note)) == NOTE_REFUSED


@pytest.mark.parametrize("source_note", [
    "two\nlines", "ends in a break\n", "carriage\rreturn", "windows\r\nbreak",
    "line\N{LINE SEPARATOR}separator", "paragraph\N{PARAGRAPH SEPARATOR}separator",
    "next\x85line", "form\x0cfeed", "vertical\x0btab",
], ids=["lf", "trailing-lf", "cr", "crlf", "line-separator", "paragraph-separator", "nel", "ff",
        "vt"])
def test_the_source_note_holds_no_line_break(tmp_path, source_note):
    """Every boundary Python splits a line at is a line break; the plan names no code points."""
    assert refusal(candidate(tmp_path, source_note=source_note)) == NOTE_BROKEN


def test_a_folded_block_in_the_file_ends_in_a_line_break_and_is_refused(tmp_path):
    folded = edited(tmp_path, f'source_note: "{OWNER_NOTE}"', "source_note: >\n  a folded note")

    assert refusal(folded) == NOTE_BROKEN


@pytest.mark.parametrize("source_note", [
    "n", "n" * 500, OWNER_NOTE, " leading and trailing ", "\N{INDIAN RUPEE SIGN}" * 500])
def test_a_source_note_within_its_bounds_is_kept_as_written(tmp_path, source_note):
    assert load_with(tmp_path, source_note=source_note).source_note == source_note


@pytest.mark.parametrize("rates", [{}, [], [["INR", "1"]], "INR", None, 5])
def test_the_rates_must_be_a_non_empty_mapping(tmp_path, rates):
    assert refusal(candidate(tmp_path, rates=rates)) == RATES_REFUSED


@pytest.mark.parametrize("currency", ["XYZ", "usd", "US", "DOLLAR", 840, None, True])
def test_a_rate_for_a_currency_layer_1_does_not_have_is_refused(tmp_path, currency):
    assert refusal(candidate(tmp_path, rates={"INR": "1", currency: "2"})) == (
        f"{FILE}: rates.{currency}: {currency!r} is not a configured ISO 4217 code")


def test_a_rate_may_be_stated_for_any_layer_1_currency_and_none_is_required(tmp_path):
    """The vocabulary is D1's, not a short list; a rate set of the base alone is valid."""
    assert with_rates(tmp_path, ZWG="0.5").rates["ZWG"] == Decimal("0.5")
    assert dict(load_with(tmp_path, rates={"INR": "1"}).rates) == {"INR": Decimal("1")}


# ---------------------------------------------------------------------------
# Loader refusals: a rate (plan A7.2, A7.3 item 2)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("rate", [85.5, 85.0, 0.012])
def test_a_rate_written_as_a_yaml_float_is_refused(tmp_path, rate):
    """A binary float is not the number the author wrote, even when it is integral."""
    assert refusal(candidate(tmp_path, rates={"INR": "1", "USD": rate})) == not_a_rate("float")


@pytest.mark.parametrize("written", ["85.5", "85.0", ".5", "8.5e+1", ".inf", ".nan"])
def test_an_unquoted_decimal_in_the_file_is_a_float_and_is_refused(tmp_path, written):
    """The authoring mistake itself: a rate without its quotes."""
    assert refusal(edited(tmp_path, 'USD: "85"', f"USD: {written}")) == not_a_rate("float")


def test_the_base_rate_is_refused_as_a_float_before_it_is_compared_with_1(tmp_path):
    assert refusal(edited(tmp_path, 'INR: "1"', "INR: 1.0")) == not_a_rate("float", "INR")


@pytest.mark.parametrize(("written", "kind"), [
    ("true", "bool"), ("yes", "bool"), ("", "NoneType"), ("[85]", "list"), ("{a: 1}", "dict"),
    ("2026-10-01", "date"),
])
def test_a_rate_that_is_neither_a_string_nor_an_integer_is_refused(tmp_path, written, kind):
    assert refusal(edited(tmp_path, 'USD: "85"', f"USD: {written}")) == not_a_rate(kind)


def test_a_boolean_is_not_the_integer_1_and_cannot_stand_for_the_base_rate(tmp_path):
    """bool is a subclass of int, and Decimal(True) is 1: `INR: true` must not pass as a rate."""
    assert refusal(edited(tmp_path, 'INR: "1"', "INR: true")) == not_a_rate("bool", "INR")
    assert refusal(candidate(tmp_path, rates={"INR": "1", "USD": False})) == not_a_rate("bool")


@pytest.mark.parametrize("rate", [
    "", "abc", "85 INR", "85,5", "1,000", "85.5.5", "eighty-five", "0o125", "0x55",
    # Everything Decimal() would accept and an author would not mean.
    "NaN", "sNaN", "Infinity", "-Infinity", "inf", "1E+2", "1e2", "1E-9", "8.5e1", "+85", " 85",
    "85 ", "85\n", "8_5", ".5", "5.", "--85",
    "\N{ARABIC-INDIC DIGIT EIGHT}\N{ARABIC-INDIC DIGIT FIVE}",
    "\N{FULLWIDTH DIGIT EIGHT}\N{FULLWIDTH DIGIT FIVE}", "\N{VULGAR FRACTION ONE HALF}",
])
def test_a_rate_string_must_be_a_plain_decimal_number(tmp_path, rate):
    """
    Digits, and optionally a point and digits: nothing a reader has to
    interpret. The plan fixes no grammar for a rate string, so the loader
    takes the narrowest one in which "integer digits" and "decimal places"
    can be counted as written.
    """
    assert refusal(candidate(tmp_path, rates={"INR": "1", "USD": rate})) == (
        f"{FILE}: rates.USD: {rate!r} is not a plain decimal number")


def test_an_unquoted_exponent_in_the_file_is_a_string_and_is_still_refused(tmp_path):
    """PyYAML reads `1e2` as the string "1e2", not as a float."""
    assert refusal(edited(tmp_path, 'USD: "85"', "USD: 1e2")) == (
        f"{FILE}: rates.USD: '1e2' is not a plain decimal number")


@pytest.mark.parametrize("rate", ["0", 0, "0.0", "0.00000000", "-85", -85, "-0.01", "-0",
                                  "-0.00000001"])
def test_a_rate_must_be_positive(tmp_path, rate):
    """There is no zero and no negative rate: neither is a price."""
    assert refusal(candidate(tmp_path, rates={"INR": "1", "USD": rate})) == NOT_POSITIVE


@pytest.mark.parametrize("rate", ["0.123456789", "85.000000000", "85.000000001", "1.999999999"])
def test_a_rate_holds_at_most_8_decimal_places(tmp_path, rate):
    """Counted as written: nine places are nine, whatever their digits."""
    assert refusal(candidate(tmp_path, rates={"INR": "1", "USD": rate})) == TOO_PRECISE


@pytest.mark.parametrize("rate", ["10000000000", 10000000000, "12345678901.5", "99999999999.9",
                                  "00000000085"])
def test_a_rate_holds_at_most_10_integer_digits(tmp_path, rate):
    """Integer digits, not total digits: eleven before the point are refused at any scale."""
    assert refusal(candidate(tmp_path, rates={"INR": "1", "USD": rate})) == TOO_LARGE


@pytest.mark.parametrize(("rate", "loaded"), [
    ("85", "85"), (85, "85"), ("085", "85"), ("0.1", "0.1"), ("0.012", "0.012"),
    ("83.2575", "83.2575"), ("0.00000001", "0.00000001"), ("0.12345678", "0.12345678"),
    ("9999999999", "9999999999"), (9999999999, "9999999999"),
    ("9999999999.99999999", "9999999999.99999999"),
])
def test_a_rate_within_its_bounds_loads_as_the_exact_decimal_the_author_wrote(
        tmp_path, rate, loaded):
    usd = with_rates(tmp_path, USD=rate).rates["USD"]

    assert type(usd) is Decimal
    assert usd == Decimal(loaded)


def test_an_unquoted_integer_in_the_file_is_a_rate(tmp_path):
    """Plan A7.3 item 2: a YAML string or integer."""
    assert load_rate_set(edited(tmp_path, 'USD: "85"', "USD: 9999999999")).rates["USD"] == (
        Decimal("9999999999"))
    assert refusal(edited(tmp_path, 'USD: "85"', "USD: 10000000000")) == TOO_LARGE
    assert refusal(edited(tmp_path, 'USD: "85"', "USD: 0")) == NOT_POSITIVE
    assert refusal(edited(tmp_path, 'USD: "85"', "USD: -85")) == NOT_POSITIVE


@pytest.mark.parametrize(("written", "loaded"), [
    ("85", "85"), ("0125", "85"), ("0x55", "85"), ("0b1010101", "85"), ("8_5", "85"),
    ("+85", "85"), ("1:25", "85"), ("1_000", "1000"),
])
def test_an_unquoted_integer_is_the_number_yaml_resolves_whatever_its_notation(
        tmp_path, written, loaded):
    """
    The plan admits a YAML integer, and YAML 1.1 spells one in octal, hex,
    binary and base 60 as well as in decimal: an unquoted 0125 is 85. The
    loader sees the number, never the spelling, so the committed file quotes
    every rate. Quoted, the same text is counted as written or refused.
    """
    assert load_rate_set(edited(tmp_path, 'USD: "85"', f"USD: {written}")).rates["USD"] == (
        Decimal(loaded))
    assert with_rates(tmp_path, USD="0125").rates["USD"] == Decimal("125")
    for quoted in ("0x55", "0b1010101", "8_5", "+85", "1:25"):
        assert refusal(candidate(tmp_path, rates={"INR": "1", "USD": quoted})) == (
            f"{FILE}: rates.USD: {quoted!r} is not a plain decimal number")


def test_an_integer_of_any_size_is_refused_as_a_rate_and_as_nothing_else(tmp_path):
    """Bounded as a number: ten thousand hex digits never reach a string conversion."""
    assert refusal(edited(tmp_path, 'USD: "85"', "USD: 0x" + "f" * 10_000)) == TOO_LARGE
    assert refusal(edited(tmp_path, 'USD: "85"', "USD: -0x" + "f" * 10_000)) == NOT_POSITIVE


@pytest.mark.parametrize(("change", "base"), [
    ({"rates": {"USD": "85", "EUR": "100"}}, "INR"),
    ({"base_currency": "GBP"}, "GBP"),
])
def test_the_base_currency_must_have_a_rate(tmp_path, change, base):
    assert refusal(candidate(tmp_path, **change)) == (
        f"{FILE}: rates: no rate for the base currency {base}")


@pytest.mark.parametrize("rate", ["2", 2, "1.00000001", "0.99999999", "85"])
def test_the_base_currencys_rate_must_be_exactly_1(tmp_path, rate):
    assert refusal(candidate(tmp_path, rates={"INR": rate, "USD": "85"})) == BASE_NOT_ONE


@pytest.mark.parametrize("rate", ["1", 1, "1.0", "1.00000000"])
def test_a_base_rate_that_is_numerically_1_is_exactly_1(tmp_path, rate):
    """Exactly 1 is a statement about the number, as the digest's decimal text is."""
    assert load_with(tmp_path, rates={"INR": rate, "USD": "85"}).rates["INR"] == 1


def test_one_bad_rate_refuses_the_whole_file(tmp_path):
    """Nothing half-loads: there is no rate set holding the rates that were fine."""
    assert refusal(candidate(tmp_path, rates={"INR": "1", "USD": "85", "EUR": 100.5})) == (
        not_a_rate("float", "EUR"))


# ---------------------------------------------------------------------------
# Conversion (plan A7.5 items 1 and 2, A9.1)
# ---------------------------------------------------------------------------


def test_the_named_constants_are_the_plans():
    assert ARITHMETIC_PRECISION == 50
    assert ROUNDING_MODE == ROUND_HALF_EVEN
    assert (BASE_QUANTUM, BASE_QUANTUM.as_tuple().exponent) == (Decimal("0.01"), -2)


def test_the_arithmetic_context_is_explicit_and_shared_with_nothing():
    context = arithmetic_context()

    assert (context.prec, context.rounding) == (50, ROUND_HALF_EVEN)
    assert (context.Emin, context.Emax) == (decimal.MIN_EMIN, decimal.MAX_EMAX)
    assert {signal for signal, trapped in context.traps.items() if trapped} == {
        decimal.InvalidOperation, decimal.DivisionByZero, decimal.Overflow}
    assert arithmetic_context() is not context
    context.prec = 3
    assert arithmetic_context().prec == 50


@pytest.mark.parametrize(("amount", "currency", "base"), [
    # DEAL-001, the CRITICAL customer's one open deal (plan Appendix 2): 5361.44 x 85.
    ("5361.44", "USD", "455722.40"),
    # The open pipeline's USD and EUR totals, unweighted and weighted (plan Appendix 1 and 2).
    ("193373.46", "USD", "16436744.10"),
    ("96633.33", "EUR", "9663333.00"),
    ("38653.33", "EUR", "3865333.00"),
    ("1", "USD", "85.00"),
    ("0.01", "USD", "0.85"),
    ("0", "USD", "0.00"),
    ("0.00", "EUR", "0.00"),
    ("-5361.44", "USD", "-455722.40"),
])
def test_an_amount_converts_at_the_committed_rate_to_a_hand_computed_value(
        committed, amount, currency, base):
    assert converted(amount, currency, committed) == base


@pytest.mark.parametrize(("amount", "base"), [
    ("47342500.00", "47342500.00"), ("47342500", "47342500.00"), ("5", "5.00"), ("0.1", "0.10"),
    ("1.005", "1.00"), ("1.015", "1.02"), ("2.675", "2.68"), ("100.025", "100.02"),
    ("100.0251", "100.03"), ("0", "0.00"),
])
def test_a_base_currency_amount_is_multiplied_by_1_and_quantized_the_same_way(
        committed, amount, base):
    """2.675 is 2.68 half-even and 2.67 through a binary float; 1.005 is 1.00, not 1.01."""
    assert converted(amount, "INR", committed) == base


@pytest.mark.parametrize(("amount", "currency", "base"), [
    # 0.085 and 0.255: half-up gives 0.09 and 0.26, truncation 0.08 and 0.25.
    ("0.001", "USD", "0.08"), ("0.003", "USD", "0.26"),
    # 0.0867 is no tie: 0.09, where ROUND_05UP and truncation give 0.08.
    ("0.00102", "USD", "0.09"),
    # 0.125 and 0.135: 0.12 and 0.14.
    ("0.00125", "EUR", "0.12"), ("0.00135", "EUR", "0.14"),
    # Below zero the even neighbour is the same distance away: floor and ceiling differ.
    ("-0.001", "USD", "-0.08"), ("-0.003", "USD", "-0.26"),
])
def test_half_a_quantum_rounds_to_the_even_neighbour_at_the_committed_rates(
        committed, amount, currency, base):
    assert converted(amount, currency, committed) == base


@pytest.mark.parametrize(("amount", "base"), [
    # At a rate of 0.5 these products are exactly 0.005, 0.015, 0.025 and 0.035.
    ("0.01", "0.00"), ("0.03", "0.02"), ("0.05", "0.02"), ("0.07", "0.04"),
    # 0.0251 and 0.0249 are either side of a half: the nearer neighbour, with no tie to break.
    ("0.0502", "0.03"), ("0.0498", "0.02"),
])
def test_half_a_quantum_rounds_to_the_even_neighbour_on_two_place_amounts(tmp_path, amount, base):
    """Half-up would give 0.01, 0.02, 0.03, 0.04; half-down 0.00, 0.01, 0.02, 0.03."""
    assert converted(amount, "GBP", with_rates(tmp_path, GBP="0.5")) == base


@pytest.mark.parametrize(("rate", "base", "at_28_digits"), [
    # 999999999999999 cents x 999999997949999999 / 10^8 = ...00000.2050000001 in units.
    ("9999999979.49999999", "99999999794999899900000.21", "99999999794999899900000.20"),
    # 999999999999999 cents x 999999996450000001 / 10^8 = ...00000.3549999999 in units.
    ("9999999964.50000001", "99999999644999900100000.35", "99999999644999900100000.36"),
])
def test_conversion_is_exact_where_the_default_precision_of_28_is_not(
        tmp_path, rate, base, at_28_digits):
    """
    The largest amount Numeric(15, 2) holds, at a rate of 10 integer digits
    and 8 decimal places: a product of 33 significant digits. The expected
    amount is worked out with integers. At 28 digits the product is rounded
    before it is quantized, and the last cent comes out wrong in each direction.
    """
    cents, remainder = divmod(999999999999999 * int(rate.replace(".", "")), 10 ** 8)
    by_integers = cents + (1 if remainder * 2 > 10 ** 8 else 0)
    assert remainder * 2 != 10 ** 8 and f"{by_integers // 100}.{by_integers % 100:02d}" == base

    assert converted("9999999999999.99", "USD", with_rates(tmp_path, USD=rate)) == base

    with localcontext(Context(prec=28, rounding=ROUND_HALF_EVEN)):
        default = (Decimal("9999999999999.99") * Decimal(rate)).quantize(Decimal("0.01"))
    assert str(default) == at_28_digits != base, "the case must be able to fail"


@pytest.mark.parametrize("ambient", [
    Context(prec=5, rounding=ROUND_UP), Context(prec=3, rounding=ROUND_CEILING),
    Context(prec=28, rounding=ROUND_UP), Context(prec=28, rounding=ROUND_DOWN),
    Context(prec=28, traps=[Inexact, Rounded]),
], ids=["prec-5-up", "prec-3-ceiling", "prec-28-up", "prec-28-down", "traps"])
def test_the_callers_decimal_context_cannot_change_a_figure_or_be_changed(
        tmp_path, committed, ambient):
    """Plan A9.1: the process default context is never relied on, and never altered."""
    wide = load_with(tmp_path, **WIDE)

    with localcontext(ambient):
        figures = [converted("5361.44", "USD", committed), converted("96633.33", "EUR", committed),
                   converted("0.001", "USD", committed), converted("0.003", "USD", committed),
                   converted("2.675", "INR", committed),
                   converted("9999999999999.99", "USD", wide)]
        after = getcontext()
        assert (after.prec, after.rounding, after.traps) == (
            ambient.prec, ambient.rounding, ambient.traps)

    assert figures == ["455722.40", "9663333.00", "0.08", "0.26", "2.68",
                       "99999999794999899900000.21"]


def test_convert_leaves_the_default_context_as_it_found_it(committed):
    before = (getcontext().prec, getcontext().rounding, dict(getcontext().traps))

    assert converted("193373.46", "USD", committed) == "16436744.10"

    assert (getcontext().prec, getcontext().rounding, dict(getcontext().traps)) == before


def test_convert_returns_a_new_money_value_and_leaves_its_input_alone(committed):
    value = MoneyValue(Decimal("5361.44"), "USD")
    in_base = MoneyValue(Decimal("5.00"), "INR")

    result, same_currency = convert(value, committed), convert(in_base, committed)

    assert type(result) is MoneyValue and result is not value
    assert (value.amount, value.currency) == (Decimal("5361.44"), "USD")
    assert str(value.amount) == "5361.44"
    assert same_currency == in_base and same_currency is not in_base
    assert committed.digest == PIN


def test_the_base_currency_is_data_and_another_base_needs_no_code_change(tmp_path):
    """SD-1: the base is declared by the rate set. Nothing in the code says INR."""
    usd_based = load_with(tmp_path, base_currency="USD",
                          rates={"USD": "1", "INR": "0.0125", "EUR": "1.25"})

    assert usd_based.digest == "5c6014e1de104601b738d6feb24b2a020eb7f44f60e5eb41c51fba5eef96eafe"
    assert [converted(amount, currency, usd_based) for amount, currency in [
        ("100.00", "INR"), ("10.00", "EUR"), ("0.40", "INR"), ("1.20", "INR"), ("7.00", "USD"),
    ]] == ["1.25", "12.50", "0.00", "0.02", "7.00"]


def test_a_changed_rate_changes_the_converted_amount(tmp_path, committed):
    """The rate is live: nothing is hard-wired to 85."""
    assert converted("100", "USD", committed) == "8500.00"
    assert converted("100", "USD", with_rates(tmp_path, USD="83.2575")) == "8325.75"


def test_convert_uses_the_rate_set_it_is_given_and_loads_none(tmp_path, monkeypatch, fresh_default):
    """Plan A22.5: the rate set is an argument. Only a service obtains the default."""
    monkeypatch.setattr(rates_module, "DEFAULT_RATE_SET_PATH", tmp_path / "absent.yaml")

    assert converted("1", "USD", with_rates(tmp_path, USD="2")) == "2.00"
    assert default_rate_set.cache_info().currsize == 0


# ---------------------------------------------------------------------------
# A missing rate (plan A7.5 item 3)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("amount", "currency"), [
    ("1000.00", "GBP"), ("1.00", "JPY"), ("1.00", "AED"), ("1.00", "ZWG"), ("0", "GBP"),
    ("-1.00", "GBP"),
])
def test_a_currency_the_rate_set_does_not_hold_raises_and_is_never_defaulted(
        committed, amount, currency):
    """Each is a Layer 1 currency with no rate stated. A zero amount is refused like any other."""
    assert currency in default_config().currency_codes and currency not in committed.rates

    with pytest.raises(FxRateMissingError) as missing:
        convert(MoneyValue(Decimal(amount), currency), committed)

    assert missing.value.currencies == (currency,)
    assert type(missing.value.currencies) is tuple
    assert missing.value.rate_set_version == "1"
    assert isinstance(missing.value, FxError)
    assert not isinstance(missing.value, KeyError | FxConfigError)
    assert str(missing.value) == f"rate set '1' holds no rate for {currency}"


def test_a_rate_set_of_the_base_alone_converts_the_base_and_nothing_else(tmp_path):
    base_alone = load_with(tmp_path, rate_set_version="9", rates={"INR": "1"})

    assert converted("1.00", "INR", base_alone) == "1.00"
    with pytest.raises(FxRateMissingError) as missing:
        convert(MoneyValue(Decimal("1.00"), "USD"), base_alone)
    assert (missing.value.currencies, missing.value.rate_set_version) == (("USD",), "9")


def test_the_missing_rate_error_carries_its_currencies_ascending_and_once_each():
    """One error can carry every missing currency: what a later service raises once (A7.5.4)."""
    error = FxRateMissingError(["JPY", "GBP", "JPY", "CHF"], "1")

    assert error.currencies == ("CHF", "GBP", "JPY")
    assert type(error.currencies) is tuple
    assert error.rate_set_version == "1"
    assert str(error) == "rate set '1' holds no rate for CHF, GBP, JPY"


def test_a_single_code_is_one_missing_currency_and_not_its_letters():
    assert FxRateMissingError("GBP", "1").currencies == ("GBP",)


def test_a_refused_file_and_a_missing_rate_are_different_failures():
    """A configuration fault is not a conversion failure: the D1, D2 and M1 convention."""
    assert issubclass(FxRateMissingError, FxError)
    assert not issubclass(FxConfigError, FxError)
    assert not issubclass(FxError, FxConfigError)
    assert not issubclass(FxRateMissingError, FxConfigError)
    assert (FxError.__bases__, FxRateMissingError.__bases__, FxConfigError.__bases__) == (
        (Exception,), (FxError,), (Exception,))


# ---------------------------------------------------------------------------
# MoneyValue is unchanged (plan A7.1 item 4, A7.5 items 1 and 5; X9)
# ---------------------------------------------------------------------------


def test_adding_two_currencies_still_raises_with_a_rate_set_loaded(committed):
    usd, inr = MoneyValue(Decimal("1"), "USD"), MoneyValue(Decimal("1"), "INR")

    with pytest.raises(CurrencyMismatchError):
        usd + inr
    with pytest.raises(CurrencyMismatchError):
        inr - usd
    with pytest.raises(CurrencyMismatchError):
        MoneyValue.total("INR", [inr, usd])
    with pytest.raises(CurrencyMismatchError):
        convert(usd, committed) + usd


def test_converted_amounts_total_in_the_base_currency_through_money_value(committed):
    """Plan A7.5 item 5: base amounts are summed with MoneyValue.total(base_currency, ...)."""
    in_base = [convert(MoneyValue(Decimal(amount), currency), committed)
               for amount, currency in [("47342500.00", "INR"), ("5361.44", "USD"),
                                        ("96633.33", "EUR")]]

    total = MoneyValue.total("INR", in_base)

    assert (str(total.amount), total.currency) == ("57461555.40", "INR")


def test_money_value_gained_no_conversion_of_its_own():
    """FX plugs in beside MoneyValue, as a separate explicit function (X9)."""
    assert {name for name in vars(MoneyValue) if not name.startswith("_")} == {"total"}
    assert [field.name for field in dataclasses.fields(MoneyValue)] == ["amount", "currency"]


def test_money_value_still_refuses_a_currency_layer_1_does_not_have():
    """So no such amount can be built, and none can reach convert()."""
    with pytest.raises(ContractViolationError, match="not a configured ISO 4217 code"):
        MoneyValue(Decimal("1"), "XYZ")
