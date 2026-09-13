from datetime import date, time
from decimal import Decimal

import pytest

from colf_manager.validation import (
    nonnegative_decimal,
    nonnegative_int,
    parse_date,
    parse_time,
    validate_password,
    validate_work_times,
)


def test_parse_date_valid_and_invalid():
    assert parse_date("2026-09-13", "Data") == date(2026, 9, 13)
    with pytest.raises(ValueError, match="data non valida"):
        parse_date("13/09/2026", "Data")


def test_parse_time_valid_and_invalid():
    assert parse_time("09:30", "Ora") == time(9, 30)
    with pytest.raises(ValueError, match="ora non valida"):
        parse_time("25:00", "Ora")


def test_nonnegative_decimal_validation():
    assert nonnegative_decimal("1.25", "Importo") == Decimal("1.25")
    assert nonnegative_decimal("", "Importo") == Decimal("0")
    with pytest.raises(ValueError, match="numero non valido"):
        nonnegative_decimal("abc", "Importo")
    with pytest.raises(ValueError, match=">= 0"):
        nonnegative_decimal("-0.01", "Importo")


def test_nonnegative_int_validation():
    assert nonnegative_int("4", "Pausa") == 4
    assert nonnegative_int(None, "Pausa") == 0
    with pytest.raises(ValueError, match="intero non valido"):
        nonnegative_int("1.5", "Pausa")
    with pytest.raises(ValueError, match=">= 0"):
        nonnegative_int("-1", "Pausa")


def test_validate_work_times():
    validate_work_times(time(9), time(10), 15)
    with pytest.raises(ValueError, match="successivo"):
        validate_work_times(time(10), time(9), 0)
    with pytest.raises(ValueError, match="pausa"):
        validate_work_times(time(9), time(10), 60)


def test_validate_password():
    validate_password("Password1234")
    with pytest.raises(ValueError, match="12 caratteri"):
        validate_password("Short1")
    with pytest.raises(ValueError, match="lettere e numeri"):
        validate_password("onlylettersxx")
    with pytest.raises(ValueError, match="lettere e numeri"):
        validate_password("123456789012")
