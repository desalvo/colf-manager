from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

CENT = Decimal("0.01")


def currency_amount(value) -> str:
    """Format a monetary amount with exactly two decimal digits and comma separator."""
    try:
        amount = Decimal(str(value if value is not None else 0)).quantize(
            CENT, rounding=ROUND_HALF_UP
        )
    except (InvalidOperation, ValueError, TypeError):
        amount = Decimal("0.00")
    return f"{amount:.2f}".replace(".", ",")


def currency(value) -> str:
    return f"€ {currency_amount(value)}"
