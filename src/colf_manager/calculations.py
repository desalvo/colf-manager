from calendar import monthrange
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")


def money(value):
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def rate_on(rates, day):
    valid = [r for r in rates if r.valid_from <= day]
    return Decimal(valid[-1].amount) if valid else Decimal("0")


def monthly_summary(entries, absences, expenses, rates, year, month, tfr_factor=Decimal("13.5")):
    entries = [e for e in entries if e.work_date.year == year and e.work_date.month == month]
    worked_hours = sum((e.hours for e in entries), Decimal("0"))
    worked_pay = sum((e.hours * rate_on(rates, e.work_date) for e in entries), Decimal("0"))
    paid_absence = sum(
        (
            Decimal(a.paid_hours or 0) * rate_on(rates, a.start_date)
            for a in absences
            if a.paid and a.start_date.year == year and a.start_date.month == month
        ),
        Decimal("0"),
    )
    reimbursements = sum(
        (
            Decimal(e.amount)
            for e in expenses
            if e.expense_date.year == year and e.expense_date.month == month and not e.reimbursed
        ),
        Decimal("0"),
    )
    gross = money(worked_pay + paid_absence)
    # Configurable accounting accrual. Legal verification remains the employer's responsibility.
    tfr_accrual = money(gross / Decimal(tfr_factor)) if tfr_factor else Decimal("0")
    return {
        "worked_hours": money(worked_hours),
        "worked_pay": money(worked_pay),
        "paid_absence": money(paid_absence),
        "reimbursements": money(reimbursements),
        "gross": gross,
        "tfr_accrual": tfr_accrual,
        "payable": money(gross + reimbursements),
    }


def period_bounds(year, month):
    return date(year, month, 1), date(year, month, monthrange(year, month)[1])
