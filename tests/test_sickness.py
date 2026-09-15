from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from colf_manager.sickness_rules import sickness_metrics, sickness_rule


def worker(start=date(2024, 1, 1)):
    return SimpleNamespace(employment_start=start)


def absence(start, end, paid=True, override=False, oncological=False):
    return SimpleNamespace(
        kind="sickness",
        start_date=start,
        end_date=end,
        paid=paid,
        paid_beyond_legal_limit=override,
        oncological=oncological,
    )


def test_sickness_rule_seniority_and_oncological_protection():
    first = sickness_rule(worker(date(2026, 7, 1)), date(2026, 9, 1))
    second = sickness_rule(worker(date(2025, 1, 1)), date(2026, 9, 1))
    long = sickness_rule(worker(date(2020, 1, 1)), date(2026, 9, 1), True)
    assert first["paid_days_limit"] == Decimal("8")
    assert second["paid_days_limit"] == Decimal("10")
    assert long["paid_days_limit"] == Decimal("15")
    assert long["job_protection_days"] == Decimal("270.0")


def test_sickness_metrics_are_days_and_track_extra_paid():
    w = worker(date(2020, 1, 1))
    records = [
        absence(date(2026, 1, 1), date(2026, 1, 10)),
        absence(date(2026, 2, 1), date(2026, 2, 10), override=True),
    ]
    metrics = sickness_metrics(w, records, 2026, date(2026, 9, 15))
    assert metrics["total_year"] == Decimal("20")
    assert metrics["paid_year"] == Decimal("20")
    assert metrics["paid_days_limit"] == Decimal("15")
    assert metrics["extra_paid_year"] == Decimal("5")
    assert metrics["legal_paid_remaining"] == Decimal("0")


def test_sickness_rule_is_effective_dated_from_2013():
    assert sickness_rule(worker(date(2013, 1, 1)), date(2014, 1, 1))["known"] is True
    assert sickness_rule(worker(date(2013, 1, 1)), date(2012, 1, 1))["known"] is False
