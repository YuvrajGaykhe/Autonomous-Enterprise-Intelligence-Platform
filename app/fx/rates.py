"""
The FX rate set (VS-02 plan A7): authored configuration, loaded lazily.

A rate set is a stated assumption, never a fact: one snapshot of rates to a
declared base currency, with the date it is stated for and the author's note
on where it comes from. It lives in config/intelligence/fx_rates.yaml and
nowhere else (SD-2): there is no table, no migration and no stored copy.

    rate_set_version   identifies the set. Any change to any authored field
                       needs a new one (A7.2 rule 5)
    base_currency      the one currency every converted amount is stated in
    as_of_date         the date the assumption is stated for. It is reported
                       and never matched against a scope's as_of
    source_note        where the assumption comes from, in the author's words
    rates              units of base currency per ONE unit of each currency,
                       one rate per currency
    digest             derived: the SHA-256 of every authored field (A7.4)

The currency vocabulary is not redeclared here. It is read from the frozen
D1 configuration, the rule MoneyValue already applies, so a rate can never
be stated for a code Layer 1 would have rejected.

Unknown and missing keys are refused, and a broken file is refused naming
the broken key, or the file alone when it cannot be parsed at all (plan A7.3
item 1). A rate written as a YAML float is refused rather than converted: a
binary float is not the number the author wrote.

Nothing is read at import or at application startup. default_rate_set()
reads the file on first use and keeps the result for the process. A load
that fails is not kept, so a corrected file loads on the next call.
"""

from __future__ import annotations

import functools
import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from decimal import MAX_EMAX, MIN_EMIN, Context, Decimal, localcontext
from pathlib import Path
from types import MappingProxyType

import yaml

from app.fx.errors import FxConfigError
from app.intelligence.contract import canonical_json, decimal_text
from app.normalization.config import default_config

DEFAULT_RATE_SET_PATH = (
    Path(__file__).resolve().parents[2] / "config" / "intelligence" / "fx_rates.yaml"
)

FORMAT_VERSION = 1
#: Plan A7.2: the bounds of each authored field.
RATE_SET_VERSION_MAX_LENGTH = 50
SOURCE_NOTE_MAX_LENGTH = 500
RATE_MAX_DECIMAL_PLACES = 8
RATE_MAX_INTEGER_DIGITS = 10

_KEYS = frozenset({"version", "rate_set_version", "base_currency", "as_of_date", "source_note",
                   "rates"})
#: A rate string as its author writes it: digits, and optionally a point and
#: more digits. No exponent, no plus sign, no space and no NaN. A minus sign
#: is read only so that a negative rate is refused as one.
_PLAIN_DECIMAL = re.compile(r"-?[0-9]+(?:\.[0-9]+)?")


@dataclass(frozen=True)
class RateSet:
    """One immutable snapshot of rates to a base currency: a stated assumption."""

    rate_set_version: str
    base_currency: str
    as_of_date: date
    source_note: str
    rates: Mapping[str, Decimal]

    @property
    def digest(self) -> str:
        """
        The set's identity (plan A7.4): it covers every authored field.

        VS-01's decimal_text normalizes in the current Decimal context, so
        the digest states one of its own: as many digits as the longest rate
        holds, and the widest exponents. Normalizing is then exact and can
        raise no signal, whatever context the caller or the process default
        is in.
        """
        digits = max([1, *(len(rate.as_tuple().digits) for rate in self.rates.values())])
        with localcontext(Context(prec=digits, Emin=MIN_EMIN, Emax=MAX_EMAX)):
            rates = [[currency, decimal_text(rate)]
                     for currency, rate in sorted(self.rates.items())]
        return hashlib.sha256(canonical_json({
            "as_of_date": self.as_of_date.isoformat(),
            "base_currency": self.base_currency,
            "rate_set_version": self.rate_set_version,
            "rates": rates,
            "source_note": self.source_note,
        }).encode("utf-8")).hexdigest()


@functools.lru_cache(maxsize=1)
def default_rate_set() -> RateSet:
    """Load (once, on first use) the repository rate set."""
    return load_rate_set(DEFAULT_RATE_SET_PATH)


def load_rate_set(path: str | Path) -> RateSet:
    """Load and validate a rate-set file."""
    path = Path(path)
    where = str(path)
    if not path.is_file():
        raise FxConfigError(f"FX rate set file not found: {path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (yaml.YAMLError, ValueError) as exc:
        # ValueError is what a date that cannot exist (2026-02-30) and bytes
        # that are not UTF-8 raise: neither is a yaml.YAMLError.
        raise FxConfigError(f"{where}: invalid YAML: {exc}") from exc
    data = _exact_keys(data, where)
    version = data["version"]
    if isinstance(version, bool) or not isinstance(version, int) or version != FORMAT_VERSION:
        raise FxConfigError(f"{where}: unsupported version {version!r}")
    base_currency = _currency(data["base_currency"], f"{where}: base_currency")
    rates = _rates(data["rates"], f"{where}: rates")
    if base_currency not in rates:
        raise FxConfigError(f"{where}: rates: no rate for the base currency {base_currency}")
    if rates[base_currency] != 1:
        raise FxConfigError(
            f"{where}: rates.{base_currency}: the base currency's rate must be exactly 1"
        )
    return RateSet(
        rate_set_version=_bounded_text(data["rate_set_version"], f"{where}: rate_set_version",
                                       RATE_SET_VERSION_MAX_LENGTH),
        base_currency=base_currency,
        as_of_date=_plain_date(data["as_of_date"], f"{where}: as_of_date"),
        source_note=_single_line(data["source_note"], f"{where}: source_note"),
        rates=rates,
    )


def _rates(raw: object, loc: str) -> Mapping[str, Decimal]:
    """Every rate, read-only and ascending by currency, so no order is the file's."""
    if not isinstance(raw, dict) or not raw:
        raise FxConfigError(f"{loc}: expected a non-empty mapping")
    rates = {}
    for currency, rate in raw.items():
        rates[_currency(currency, f"{loc}.{currency}")] = _rate(rate, f"{loc}.{currency}")
    return MappingProxyType(dict(sorted(rates.items())))


def _rate(value: object, loc: str) -> Decimal:
    """
    A positive rate: a YAML string or integer (plan A7.3 item 2).

    A string is taken exactly as written, in plain decimal notation, so its
    digits are counted as its author wrote them. An integer has no written
    form left to count: it is the number YAML resolved, whatever notation
    the file spelled it in, and it is bounded as a number.

    A YAML float is refused rather than converted: it has already been
    rounded to binary, so it is not the number the author wrote.
    """
    if isinstance(value, bool) or not isinstance(value, str | int):
        raise FxConfigError(
            f"{loc}: expected a rate written as a string or an integer, "
            f"not {type(value).__name__}"
        )
    if isinstance(value, str):
        if not _PLAIN_DECIMAL.fullmatch(value):
            raise FxConfigError(f"{loc}: {value!r} is not a plain decimal number")
        integer_digits, _, decimal_places = value.partition(".")
        positive = Decimal(value) > 0
        too_precise = len(decimal_places) > RATE_MAX_DECIMAL_PLACES
        too_large = len(integer_digits) > RATE_MAX_INTEGER_DIGITS
    else:
        positive = value > 0
        too_precise = False
        too_large = value >= 10 ** RATE_MAX_INTEGER_DIGITS
    if not positive:
        raise FxConfigError(f"{loc}: expected a positive rate")
    if too_precise:
        raise FxConfigError(f"{loc}: more than {RATE_MAX_DECIMAL_PLACES} decimal places")
    if too_large:
        raise FxConfigError(f"{loc}: more than {RATE_MAX_INTEGER_DIGITS} integer digits")
    return Decimal(value)


def _currency(value: object, loc: str) -> str:
    """A code of the frozen D1 vocabulary: Layer 2 does not widen it to suit a rate."""
    if not isinstance(value, str) or value not in default_config().currency_codes:
        raise FxConfigError(f"{loc}: {value!r} is not a configured ISO 4217 code")
    return value


def _exact_keys(data: object, loc: str) -> dict[str, object]:
    """The file's mapping, after checking it has exactly the authored keys."""
    if not isinstance(data, dict):
        raise FxConfigError(f"{loc}: expected a mapping")
    missing = sorted(_KEYS - set(map(str, data)))
    unknown = sorted(set(map(str, data)) - _KEYS)
    if missing or unknown:
        raise FxConfigError(f"{loc}: missing keys {missing}, unknown keys {unknown}")
    return data


def _bounded_text(value: object, loc: str, longest: int) -> str:
    """A non-empty string, by M1's rule that a blank one is empty, within its length."""
    if not isinstance(value, str) or not value.strip() or len(value) > longest:
        raise FxConfigError(f"{loc}: expected a non-empty string of at most {longest} characters")
    return value


def _single_line(value: object, loc: str) -> str:
    """The note is the rate set's only prose, and it is one line of it."""
    note = _bounded_text(value, loc, SOURCE_NOTE_MAX_LENGTH)
    if note.splitlines() != [note]:
        raise FxConfigError(f"{loc}: expected a single line, with no line break")
    return note


def _plain_date(value: object, loc: str) -> date:
    """A calendar date, never a timestamp: the assumption is stated for a day."""
    if isinstance(value, datetime) or not isinstance(value, date):
        raise FxConfigError(f"{loc}: expected a YYYY-MM-DD date")
    return value
