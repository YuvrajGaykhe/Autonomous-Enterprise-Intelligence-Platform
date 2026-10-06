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
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

import yaml

from app.fx.rates import RateSet, load_rate_set
from app.pipeline.facts import DealFact

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
