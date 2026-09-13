from calendar import monthrange
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")


def money(value):
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def rate_on(rates, day):
    valid = sorted((r for r in rates if r.valid_from <= day), key=lambda r: r.valid_from)
    return Decimal(valid[-1].amount) if valid else Decimal("0")


def _days(start, end):
    day = start
    while day <= end:
        yield day
        day += timedelta(days=1)


def _paid_absence_value(absence, rates, period_start, period_end):
    if not absence.paid or not absence.paid_hours:
        return Decimal("0")
    overlap_start = max(absence.start_date, period_start)
    overlap_end = min(absence.end_date, period_end)
    if overlap_start > overlap_end:
        return Decimal("0")
    total_days = (absence.end_date - absence.start_date).days + 1
    hours_per_day = Decimal(absence.paid_hours) / Decimal(total_days)
    return sum(
        (hours_per_day * rate_on(rates, day) for day in _days(overlap_start, overlap_end)),
        Decimal("0"),
    )


def monthly_summary(entries, absences, expenses, rates, year, month, tfr_factor=Decimal("13.5")):
    period_start, period_end = period_bounds(year, month)
    entries = [e for e in entries if period_start <= e.work_date <= period_end]
    worked_hours = sum((e.hours for e in entries), Decimal("0"))
    worked_pay = sum((e.hours * rate_on(rates, e.work_date) for e in entries), Decimal("0"))
    paid_absence = sum(
        (_paid_absence_value(a, rates, period_start, period_end) for a in absences), Decimal("0")
    )

    worker_advances = sum(
        (
            Decimal(e.amount)
            for e in expenses
            if period_start <= e.expense_date <= period_end
            and not e.reimbursed
            and e.direction == "worker_advance"
        ),
        Decimal("0"),
    )
    employer_advances = sum(
        (
            Decimal(e.amount)
            for e in expenses
            if period_start <= e.expense_date <= period_end
            and not e.reimbursed
            and e.direction == "employer_advance"
        ),
        Decimal("0"),
    )
    expense_adjustment = worker_advances - employer_advances
    gross = money(worked_pay + paid_absence)
    tfr_accrual = money(gross / Decimal(tfr_factor)) if tfr_factor else Decimal("0")
    return {
        "worked_hours": money(worked_hours),
        "worked_pay": money(worked_pay),
        "paid_absence": money(paid_absence),
        "worker_advances": money(worker_advances),
        "employer_advances": money(employer_advances),
        "reimbursements": money(expense_adjustment),
        "gross": gross,
        "tfr_accrual": tfr_accrual,
        "payable": money(gross + expense_adjustment),
    }


def period_bounds(year, month):
    return date(year, month, 1), date(year, month, monthrange(year, month)[1])
