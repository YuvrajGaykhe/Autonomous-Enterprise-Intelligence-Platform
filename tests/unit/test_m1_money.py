"""
M1 MoneyValue: currency-qualified money that refuses a cross-currency total.

VS-01 has no FX rate set, so a number that has lost its currency is not a
fact about the business. These tests pin that losing it is impossible.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.intelligence.errors import ContractViolationError, CurrencyMismatchError
from app.intelligence.money import MoneyValue
from app.normalization.config import default_config

USD = "USD"
INR = "INR"


def test_a_money_value_keeps_its_amount_and_currency_together():
    money = MoneyValue(Decimal("5361.44"), USD)

    assert (money.amount, money.currency) == (Decimal("5361.44"), USD)


def test_rendering_is_always_currency_qualified():
    assert str(MoneyValue(Decimal("5361.44"), USD)) == "USD 5361.44"


def test_the_amount_must_be_a_decimal():
    with pytest.raises(ContractViolationError, match="must be a Decimal"):
        MoneyValue(5361.44, USD)  # type: ignore[arg-type]


@pytest.mark.parametrize("amount", ["NaN", "Infinity", "-Infinity"])
def test_a_non_finite_amount_is_refused(amount):
    with pytest.raises(ContractViolationError, match="must be finite"):
        MoneyValue(Decimal(amount), USD)


def test_the_currency_vocabulary_is_layer_1s_and_is_not_redeclared():
    assert {USD, INR, "EUR"} <= default_config().currency_codes

    with pytest.raises(ContractViolationError, match="not a configured ISO 4217 code"):
        MoneyValue(Decimal("1"), "XYZ")


def test_money_of_one_currency_adds_and_subtracts():
    assert MoneyValue(Decimal("10.50"), USD) + MoneyValue(Decimal("4.50"), USD) == MoneyValue(
        Decimal("15.00"), USD)
    assert MoneyValue(Decimal("10.50"), USD) - MoneyValue(Decimal("4.50"), USD) == MoneyValue(
        Decimal("6.00"), USD)


def test_adding_across_currencies_raises():
    with pytest.raises(CurrencyMismatchError, match="no cross-currency total exists"):
        MoneyValue(Decimal("1"), USD) + MoneyValue(Decimal("1"), INR)


def test_subtracting_across_currencies_raises():
    with pytest.raises(CurrencyMismatchError, match="no cross-currency total exists"):
        MoneyValue(Decimal("1"), USD) - MoneyValue(Decimal("1"), INR)


@pytest.mark.parametrize("other", [0, Decimal("1"), "USD 1", None])
def test_money_cannot_be_combined_with_a_non_money_value(other):
    with pytest.raises(TypeError, match="can only be combined with MoneyValue"):
        MoneyValue(Decimal("1"), USD) + other


def test_the_builtin_sum_cannot_silently_total_money():
    """sum() starts from the integer 0, which is not money in any currency, and
    MoneyValue deliberately defines no __radd__ that would quietly accept it."""
    with pytest.raises(TypeError, match="unsupported operand type"):
        sum([MoneyValue(Decimal("1"), USD), MoneyValue(Decimal("2"), USD)])


def test_total_states_the_currency_it_is_totalling():
    values = [MoneyValue(Decimal("1.25"), USD), MoneyValue(Decimal("2.75"), USD)]

    assert MoneyValue.total(USD, values) == MoneyValue(Decimal("4.00"), USD)
    assert MoneyValue.total(USD, []) == MoneyValue(Decimal("0"), USD)


def test_total_refuses_a_value_of_another_currency():
    values = [MoneyValue(Decimal("1"), USD), MoneyValue(Decimal("1"), INR)]

    with pytest.raises(CurrencyMismatchError):
        MoneyValue.total(USD, values)
