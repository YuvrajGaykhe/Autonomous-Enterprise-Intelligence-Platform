"""
Hand-built deal facts, rate sets and an arithmetic oracle for the VS-02 suites.

Not a test module.

`deal()` is one open valued deal, resolved to an owner and a customer, and
every argument changes one fact and nothing else, so a test that perturbs a
field differs from the default in that field alone.

`rate_set()` writes a rate file and loads it through app.fx's path loader,
which is the only thing that builds a rate set (plan A7.6, A25.1).

`exact_values()` is the oracle. It works the four per-deal values of plan
A9.2 and A9.3 with `fractions.Fraction` and integer rounding, and uses no
Decimal context, no app.fx and no app.pipeline code: what it returns is what
the arithmetic of the plan gives, however the application computes it.

From VS02-M3: `band()` is one stored assessment as the facts reader hands it
on, and `exact_share()`, `exact_cumulative()` and `exact_hhi()` are the
oracle for plan A11 item 5, in fractions and integer rounding again.
`exact_concentration()` works one whole block from (key, amount) pairs, and
`view_scope()` is a scope with no database behind it.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import date
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

import yaml

from app.fx.rates import RateSet, load_rate_set
from app.intelligence import Scope
from app.intelligence.scope import AsOfSource
from app.persistence.repositories.canonical import ENTITY_MODELS
from app.pipeline.facts import BandFact, DealFact

#: The D1 stage vocabulary, restated. A test pins it to the frozen configuration.
STAGES = ("negotiation", "qualification", "won")
#: The acceptance date of plan A25.1.
AS_OF = date(2026, 9, 18)

_SAME = object()


def deal(
    source_id: str = "DEAL-900",
    *,
    stage: str | None = "negotiation",
    is_active: bool = True,
    amount: str | Decimal | None = "1000.00",
    currency: str | None = "INR",
    probability: str | Decimal | None = "50.00",
    expected: date | None = date(2026, 10, 15),
    owner: str | None = "EMP-900",
    owner_key: object = _SAME,
    customer: str | None = "CUST-900",
    customer_key: object = _SAME,
) -> DealFact:
    """One deal. By default it is open, valued, owned and linked; a key defaults to what it resolves to."""
    return DealFact(
        source_id=source_id,
        stage=stage,
        is_active=is_active,
        amount=Decimal(amount) if isinstance(amount, str) else amount,
        currency=currency,
        probability=Decimal(probability) if isinstance(probability, str) else probability,
        expected_close_date=expected,
        owner_source_id=_key(owner_key, owner),
        customer_source_id=_key(customer_key, customer),
        owner=owner,
        customer=customer,
    )


def _key(key: object, resolved: str | None) -> str | None:
    """The source key a deal carries: the id it resolves to, unless the test says otherwise."""
    if key is _SAME:
        return resolved
    assert key is None or isinstance(key, str)
    return key


def rate_set(directory: Path, rates: Mapping[str, str] | None = None, *, base: str = "INR",
             version: str = "constructed") -> RateSet:
    """A rate set authored in a file of the test's own and loaded through the path loader."""
    data = {
        "version": 1,
        "rate_set_version": version,
        "base_currency": base,
        "as_of_date": date(2026, 10, 1),
        "source_note": "a rate set constructed for a test",
        "rates": {base: "1", **(rates or {})},
    }
    path = directory / f"rates-{version}.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return load_rate_set(path)


def half_even_cents(value: Fraction) -> Decimal:
    """A non-negative value rounded to 0.01, half to even, by integer arithmetic alone."""
    assert value >= 0
    cents, remainder = divmod(value * 100, 1)
    if remainder > Fraction(1, 2) or (remainder == Fraction(1, 2) and cents % 2 == 1):
        cents += 1
    return Decimal(f"{cents // 100}.{cents % 100:02d}")


def exact_values(amount: str, probability: str, rate: str) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    """(native unweighted, native weighted, base unweighted, base weighted) of plan A9.2 and A9.3."""
    native = Fraction(amount)
    weighted = half_even_cents(native * Fraction(probability) / 100)
    return (
        Decimal(amount),
        weighted,
        half_even_cents(native * Fraction(rate)),
        half_even_cents(Fraction(str(weighted)) * Fraction(rate)),
    )


def band(customer: str, stored: str = "NONE", executive_worthy: bool = False) -> BandFact:
    """One stored assessment, as written: the band is not checked here."""
    return BandFact(customer=customer, band=stored, executive_worthy=executive_worthy)


def view_scope(source_system: str = "csv_demo", as_of: date = AS_OF) -> Scope:
    """A scope with an explicit date and no database behind it."""
    return Scope(source_system=source_system, as_of=as_of, layer1_fingerprint="0" * 64,
                 as_of_source=AsOfSource.EXPLICIT, entity_counts=dict.fromkeys(ENTITY_MODELS, 0))


def half_even_places(value: Fraction, places: int = 4) -> Decimal:
    """A non-negative value rounded to `places` decimals, half to even, in integers alone."""
    assert value >= 0
    scaled, remainder = divmod(value * 10 ** places, 1)
    if remainder > Fraction(1, 2) or (remainder == Fraction(1, 2) and scaled % 2 == 1):
        scaled += 1
    return Decimal(int(scaled)).scaleb(-places)


def exact_share(amount: str | Decimal, whole: str | Decimal) -> Decimal:
    """Plan A11 item 5: the amount over the whole, rounded once to four places."""
    return half_even_places(Fraction(str(amount)) / Fraction(str(whole)))


def exact_cumulative(amounts: Iterable[str | Decimal], whole: str | Decimal) -> Decimal:
    """Plan A11 item 5: the amounts summed, then divided, then rounded once."""
    summed = sum((Fraction(str(amount)) for amount in amounts), Fraction(0))
    return half_even_places(summed / Fraction(str(whole)))


def exact_hhi(amounts: Iterable[str | Decimal], whole: str | Decimal) -> Decimal:
    """Plan A11 item 5: the sum of the squared parts, rounded once."""
    total = Fraction(str(whole))
    return half_even_places(sum(((Fraction(str(amount)) / total) ** 2 for amount in amounts),
                                Fraction(0)))


def exact_concentration(candidates: Sequence[tuple[str, str | Decimal]],
                        *, top: int = 5, points: Sequence[int] = (1, 3, 5)) -> dict[str, object]:
    """
    One whole block of plan A11 from (key, amount) pairs, as the view states it.

    Holders are the pairs above zero, by amount descending and then by key.
    The whole is the sum of every amount. Each figure is the text the view
    gives: plain notation with no trailing zeros.
    """
    def text(value: Decimal) -> str:
        if value == 0:
            return "0"
        digits = format(value, "f")
        return digits.rstrip("0").rstrip(".") if "." in digits else digits

    amounts = {key: Fraction(str(amount)) for key, amount in candidates}
    whole = sum(amounts.values(), Fraction(0))
    holders = sorted((key for key, amount in amounts.items() if amount > 0),
                     key=lambda key: (-amounts[key], key))
    if whole == 0:
        return {"holder_count": 0, "top": [], "cumulative": [], "hhi": None}
    return {
        "holder_count": len(holders),
        "top": [(key, text(half_even_places(amounts[key] / whole))) for key in holders[:top]],
        "cumulative": [(point, text(half_even_places(
            sum((amounts[key] for key in holders[:point]), Fraction(0)) / whole)))
            for point in points],
        "hhi": text(half_even_places(sum(((amounts[key] / whole) ** 2 for key in holders),
                                         Fraction(0)))),
    }
