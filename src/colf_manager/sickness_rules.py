# fmt: off
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

# Versioned contractual rules. The 2013, 2020 and 2025 renewals keep the same
# Art. 27 thresholds. Explicit effective periods prevent historical rewrites and
# make future contractual changes additive.
SICKNESS_RULES = (
    {
        "effective_from": date(2013, 7, 1),
        "effective_to": date(2020, 9, 30),
        "source": "CCNL lavoro domestico 2013, art. 26/27",
        "bands": ((6, 10, 8), (24, 45, 10), (None, 180, 15)),
    },
    {
        "effective_from": date(2020, 10, 1),
        "effective_to": date(2025, 10, 31),
        "source": "CCNL lavoro domestico 08/09/2020, art. 27",
        "bands": ((6, 10, 8), (24, 45, 10), (None, 180, 15)),
    },
    {
        "effective_from": date(2025, 11, 1),
        "effective_to": None,
        "source": "CCNL lavoro domestico 2025-2028, art. 27",
        "bands": ((6, 10, 8), (24, 45, 10), (None, 180, 15)),
    },
)


def _months_of_service(worker, as_of: date) -> int:
    start = getattr(worker, "employment_start", None)
    if not start or as_of < start:
        return 0
    months = (as_of.year - start.year) * 12 + as_of.month - start.month
    if as_of.day < start.day:
        months -= 1
    return max(0, months)


def sickness_rule(worker, as_of: date, oncological: bool = False) -> dict:
    selected = None
    for rule in SICKNESS_RULES:
        if as_of >= rule["effective_from"] and (
            rule["effective_to"] is None or as_of <= rule["effective_to"]
        ):
            selected = rule
            break
    if selected is None:
        return {"known": False, "source": "regola storica non codificata"}

    months = _months_of_service(worker, as_of)
    for max_months, protected_days, paid_days in selected["bands"]:
        if max_months is None or months <= max_months:
            protection = Decimal(str(protected_days))
            if oncological:
                protection *= Decimal("1.5")
            return {
                "known": True,
                "source": selected["source"],
                "service_months": months,
                "job_protection_days": protection,
                "paid_days_limit": Decimal(str(paid_days)),
                "oncological": bool(oncological),
                "first_three_rate": Decimal("0.50"),
                "later_rate": Decimal("1.00"),
            }
    raise AssertionError("unreachable")


def calendar_days(start: date, end: date) -> Decimal:
    if end < start:
        return Decimal("0")
    return Decimal((end - start).days + 1)


def sickness_days_in_period(absence, period_start: date, period_end: date) -> Decimal:
    start = max(absence.start_date, period_start)
    end = min(absence.end_date, period_end)
    return calendar_days(start, end) if start <= end else Decimal("0")


def sickness_metrics(worker, absences, year: int, as_of: date | None = None) -> dict:
    cutoff = min(as_of or date.today(), date(year, 12, 31))
    year_start = date(year, 1, 1)
    month_start = (
        date(cutoff.year, cutoff.month, 1) if cutoff.year == year else date(year, 12, 1)
    )
    month_end = cutoff
    history_start = min(year_start, cutoff - timedelta(days=364))
    sickness = [
        absence
        for absence in absences
        if getattr(absence, "kind", None) in {"sickness", "health"}
        and absence.start_date <= cutoff
        and absence.end_date >= history_start
    ]

    total_year = sum(
        (sickness_days_in_period(a, year_start, cutoff) for a in sickness),
        Decimal("0"),
    )
    total_month = sum(
        (sickness_days_in_period(a, month_start, month_end) for a in sickness),
        Decimal("0"),
    )
    paid_year = sum(
        (
            sickness_days_in_period(a, year_start, cutoff)
            for a in sickness
            if getattr(a, "paid", False)
        ),
        Decimal("0"),
    )
    paid_month = sum(
        (
            sickness_days_in_period(a, month_start, month_end)
            for a in sickness
            if getattr(a, "paid", False)
        ),
        Decimal("0"),
    )

    rule = sickness_rule(
        worker,
        cutoff,
        any(getattr(a, "oncological", False) for a in sickness),
    )
    legal_limit = rule.get("paid_days_limit") if rule.get("known") else None
    legal_paid_used = min(paid_year, legal_limit) if legal_limit is not None else None
    legal_remaining = (
        max(Decimal("0"), legal_limit - paid_year)
        if legal_limit is not None
        else None
    )
    extra_paid_year = (
        max(Decimal("0"), paid_year - legal_limit)
        if legal_limit is not None
        else Decimal("0")
    )

    rolling_start = cutoff - timedelta(days=364)
    protection_used = sum(
        (sickness_days_in_period(a, rolling_start, cutoff) for a in sickness),
        Decimal("0"),
    )
    protection_limit = rule.get("job_protection_days") if rule.get("known") else None
    protection_remaining = (
        max(Decimal("0"), protection_limit - protection_used)
        if protection_limit is not None
        else None
    )

    return {
        **rule,
        "total_month": total_month,
        "total_year": total_year,
        "paid_month": paid_month,
        "paid_year": paid_year,
        "extra_paid_year": extra_paid_year,
        "legal_paid_used": legal_paid_used,
        "legal_paid_remaining": legal_remaining,
        "job_protection_used_365": protection_used,
        "job_protection_remaining_365": protection_remaining,
    }
