# fmt: off
from calendar import monthrange
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")
VACATION_DAYS_YEAR = Decimal("26")
MONTHS_YEAR = Decimal("12")
WEEKS_PER_MONTH = Decimal("4.333")
TFR_DIVISOR = Decimal("13.5")


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


def _easter_sunday(year):
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    weekday_offset = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * weekday_offset) // 451
    month = (h + weekday_offset - 7 * m + 114) // 31
    day = ((h + weekday_offset - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def italian_national_holidays(year):
    easter_monday = _easter_sunday(year) + timedelta(days=1)
    return {
        date(year, 1, 1), date(year, 1, 6), easter_monday,
        date(year, 4, 25), date(year, 5, 1), date(year, 6, 2),
        date(year, 8, 15), date(year, 11, 1), date(year, 12, 8),
        date(year, 12, 25), date(year, 12, 26),
    }


def vacation_working_days(start, end):
    holidays = set()
    for year in range(start.year, end.year + 1):
        holidays |= italian_national_holidays(year)
    return sum(1 for day in _days(start, end) if day.weekday() != 6 and day not in holidays)


def vacation_hours_per_day(worker):
    monthly_hours = Decimal(worker.weekly_hours or 0) * WEEKS_PER_MONTH
    return (monthly_hours / VACATION_DAYS_YEAR) if monthly_hours else Decimal("0")


def _service_days_in_month(worker, year, month, as_of):
    month_start = date(year, month, 1)
    month_end = date(year, month, monthrange(year, month)[1])
    start = max(month_start, worker.employment_start)
    end = min(month_end, as_of, worker.employment_end or month_end)
    return max(0, (end - start).days + 1) if start <= end else 0


def vacation_accrued_days(worker, year, as_of=None):
    year_end = date(year, 12, 31)
    cutoff = min(as_of or date.today(), year_end, worker.employment_end or year_end)
    if cutoff < max(worker.employment_start, date(year, 1, 1)):
        return Decimal("0.00")
    credited_months = sum(
        1 for month in range(1, 13)
        if _service_days_in_month(worker, year, month, cutoff) >= 15
    )
    return (VACATION_DAYS_YEAR * Decimal(credited_months) / MONTHS_YEAR).quantize(CENT)


def vacation_used_days(absences, year, as_of=None):
    year_start, year_end = date(year, 1, 1), date(year, 12, 31)
    cutoff = min(as_of or year_end, year_end)
    total = 0
    for absence in absences:
        if absence.kind != "vacation":
            continue
        start = max(absence.start_date, year_start)
        end = min(absence.end_date, cutoff)
        if start <= end:
            total += vacation_working_days(start, end)
    return Decimal(total).quantize(CENT)


def vacation_balance(worker, absences, year, as_of=None):
    today = date.today()
    current_cutoff = min(as_of or today, date(year, 12, 31))
    accrued = vacation_accrued_days(worker, year, current_cutoff)
    projected = vacation_accrued_days(worker, year, date(year, 12, 31))
    used_to_date = vacation_used_days(absences, year, current_cutoff)
    used_scheduled = vacation_used_days(absences, year, date(year, 12, 31))
    usable = projected if worker.vacation_advance_allowed else accrued
    used_for_usable = used_scheduled if worker.vacation_advance_allowed else used_to_date
    return {
        "accrued": accrued,
        "projected": projected,
        "used_to_date": used_to_date,
        "used_scheduled": used_scheduled,
        "available_accrued": (accrued - used_to_date).quantize(CENT),
        "available_usable": (usable - used_for_usable).quantize(CENT),
        "advance_allowed": bool(worker.vacation_advance_allowed),
    }


def _paid_absence_value(absence, rates, period_start, period_end):
    if not absence.paid or not absence.paid_hours:
        return Decimal("0")
    overlap_start = max(absence.start_date, period_start)
    overlap_end = min(absence.end_date, period_end)
    if overlap_start > overlap_end:
        return Decimal("0")
    total_days = (absence.end_date - absence.start_date).days + 1
    hours_per_day = Decimal(absence.paid_hours) / Decimal(total_days)
    return sum((hours_per_day * rate_on(rates, day) for day in _days(overlap_start, overlap_end)), Decimal("0"))


def monthly_summary(entries, absences, expenses, rates, year, month, tfr_factor=TFR_DIVISOR):
    period_start, period_end = period_bounds(year, month)
    entries = [e for e in entries if period_start <= e.work_date <= period_end]
    worked_hours = sum((e.hours for e in entries), Decimal("0"))
    worked_pay = sum((e.hours * rate_on(rates, e.work_date) for e in entries), Decimal("0"))
    paid_absence = sum((_paid_absence_value(a, rates, period_start, period_end) for a in absences), Decimal("0"))
    worker_advances = sum((Decimal(e.amount) for e in expenses if period_start <= e.expense_date <= period_end and not e.reimbursed and e.direction == "worker_advance"), Decimal("0"))
    employer_advances = sum((Decimal(e.amount) for e in expenses if period_start <= e.expense_date <= period_end and not e.reimbursed and e.direction == "employer_advance"), Decimal("0"))
    expense_adjustment = worker_advances - employer_advances
    gross = money(worked_pay + paid_absence)
    thirteenth_accrual = money(gross / Decimal("12"))
    tfr_useful = money(gross + thirteenth_accrual)
    tfr_accrual = money(tfr_useful / Decimal(tfr_factor)) if tfr_factor else Decimal("0")
    return {
        "worked_hours": money(worked_hours), "worked_pay": money(worked_pay),
        "paid_absence": money(paid_absence), "worker_advances": money(worker_advances),
        "employer_advances": money(employer_advances), "reimbursements": money(expense_adjustment),
        "gross": gross, "thirteenth_accrual": thirteenth_accrual,
        "tfr_useful_compensation": tfr_useful, "tfr_accrual": tfr_accrual,
        "payable": money(gross + expense_adjustment),
    }


def annual_summary(entries, absences, expenses, rates, year, tfr_factor=TFR_DIVISOR):
    months = [monthly_summary(entries, absences, expenses, rates, year, m, tfr_factor) for m in range(1, 13)]
    keys = ["worked_hours", "worked_pay", "paid_absence", "worker_advances", "employer_advances", "reimbursements", "gross", "payable"]
    total = {k: money(sum((m[k] for m in months), Decimal("0"))) for k in keys}
    total["thirteenth_accrual"] = money(total["gross"] / Decimal("12"))
    total["tfr_useful_compensation"] = money(total["gross"] + total["thirteenth_accrual"])
    total["tfr_accrual"] = money(total["tfr_useful_compensation"] / Decimal(tfr_factor)) if tfr_factor else Decimal("0")
    total["months"] = months
    return total


def tfr_year_summary(worker, entries, absences, expenses, rates, year, as_of=None, tfr_factor=TFR_DIVISOR):
    cutoff = min(as_of or date.today(), date(year, 12, 31))
    filtered_entries = [e for e in entries if e.work_date <= cutoff]
    filtered_absences = [a for a in absences if a.start_date <= cutoff]
    filtered_expenses = [e for e in expenses if e.expense_date <= cutoff]
    annual = annual_summary(filtered_entries, filtered_absences, filtered_expenses, rates, year, tfr_factor)
    return {**annual, "cutoff": cutoff, "rule": "retribuzione utile annua / 13,5", "revaluation_note": "La quota maturata nell'anno non viene rivalutata. Le quote degli anni precedenti rimaste accantonate richiedono rivalutazione: 1,5% fisso + 75% dell'incremento FOI ISTAT dicembre/dicembre."}


def period_bounds(year, month):
    return date(year, month, 1), date(year, month, monthrange(year, month)[1])


INPS_TABLES = {
    2025: {
        "bands": [(Decimal("9.48"), Decimal("1.68"), Decimal("0.42")), (Decimal("11.54"), Decimal("1.89"), Decimal("0.48")), (None, Decimal("2.30"), Decimal("0.58"))],
        "over25": (Decimal("1.22"), Decimal("0.31")),
        "source": "INPS 2025 - circolare n. 29/2025",
    },
    2026: {
        "bands": [(Decimal("9.61"), Decimal("1.70"), Decimal("0.43")), (Decimal("11.70"), Decimal("1.92"), Decimal("0.48")), (None, Decimal("2.34"), Decimal("0.59"))],
        "over25": (Decimal("1.24"), Decimal("0.31")),
        "source": "INPS 2026 - circolare n. 9/2026",
    },
}


def thirteenth_year_summary(worker, entries, absences, expenses, rates, year, as_of=None):
    cutoff = min(as_of or date.today(), date(year, 12, 31))
    e = [x for x in entries if x.work_date <= cutoff]
    a = [x for x in absences if x.start_date <= cutoff]
    x = [x for x in expenses if x.expense_date <= cutoff]
    annual = annual_summary(e, a, x, rates, year)
    return {
        "cutoff": cutoff,
        "gross": annual["gross"],
        "months": annual["months"],
        "thirteenth": annual["thirteenth_accrual"],
        "formula": "retribuzione annua utile / 12",
    }


def _inps_hourly_amount(year, effective_hourly, weekly_hours):
    table = INPS_TABLES.get(year)
    if not table:
        return None
    if Decimal(weekly_hours or 0) > Decimal("24"):
        total, worker = table["over25"]
        return total, worker, table["source"]
    for ceiling, total, worker in table["bands"]:
        if ceiling is None or effective_hourly <= ceiling:
            return total, worker, table["source"]
    return None


def inps_contribution_summary(worker, annual, year):
    if not worker.inps_number or not worker.contract_number:
        return None
    hours = Decimal(annual.get("worked_hours") or 0)
    if hours <= 0:
        return {"hours": money(0), "total": money(0), "worker_share": money(0), "employer_share": money(0), "worker_due": money(0), "source": "nessuna ora registrata", "estimated": True}
    base_hourly = Decimal(annual["gross"]) / hours if hours else Decimal("0")
    effective_hourly = base_hourly + (base_hourly / Decimal("12"))
    row = _inps_hourly_amount(year, effective_hourly, worker.weekly_hours)
    if row is None:
        return {"hours": money(hours), "effective_hourly": money(effective_hourly), "unavailable": True, "estimated": True, "source": f"tabella automatica non disponibile per {year}"}
    total_rate, worker_rate, source = row
    if getattr(worker, "contract_type", "permanent") == "fixed_term":
        # INPS applies a 1.4% additional contribution for fixed-term domestic work,
        # except replacement contracts. The worker share is unchanged.
        total_rate = money(total_rate + (effective_hourly * Decimal("0.014")))
    total = money(hours * total_rate)
    worker_share = money(hours * worker_rate)
    employer_share = money(total - worker_share)
    covered = bool(getattr(worker, "employer_covers_all_taxes", False))
    return {
        "hours": money(hours), "effective_hourly": money(effective_hourly),
        "total_rate": money(total_rate), "worker_rate": money(worker_rate),
        "total": total, "worker_share": worker_share, "employer_share": employer_share,
        "worker_due": money(0) if covered else worker_share,
        "employer_cost": total if covered else employer_share,
        "employer_covers_all_taxes": covered, "source": source, "estimated": True,
    }


def estimated_irpef_summary(worker, annual, year):
    """Indicative national gross IRPEF only; final tax needs full tax-return context."""
    income = Decimal(annual.get("gross") or 0) + Decimal(annual.get("thirteenth_accrual") or 0)
    if year >= 2026:
        brackets = [(Decimal("28000"), Decimal("0.23")), (Decimal("50000"), Decimal("0.33")), (None, Decimal("0.43"))]
    else:
        brackets = [(Decimal("28000"), Decimal("0.23")), (Decimal("50000"), Decimal("0.35")), (None, Decimal("0.43"))]
    remaining = income
    lower = Decimal("0")
    gross_tax = Decimal("0")
    for ceiling, rate in brackets:
        taxable = remaining if ceiling is None else min(remaining, ceiling-lower)
        if taxable > 0:
            gross_tax += taxable * rate
            remaining -= taxable
        if ceiling is None or remaining <= 0:
            break
        lower = ceiling
    gross_tax = money(gross_tax)
    covered = bool(getattr(worker, "employer_covers_all_taxes", False))
    return {
        "taxable_income_estimate": money(income), "gross_irpef_estimate": gross_tax,
        "worker_due_estimate": money(0) if covered else gross_tax,
        "employer_assumed_tax_cost": gross_tax if covered else money(0),
        "employer_covers_all_taxes": covered,
        "note": "Stima della sola IRPEF lorda nazionale. Non include detrazioni, deduzioni, altri redditi, crediti, addizionali regionali/comunali o conguagli; l'imposta effettiva deriva dalla dichiarazione del lavoratore.",
    }


def combined_thirteenth_tfr_summary(worker, entries, absences, expenses, rates, year, as_of=None, tfr_factor=TFR_DIVISOR):
    th = thirteenth_year_summary(worker, entries, absences, expenses, rates, year, as_of)
    tfr = tfr_year_summary(worker, entries, absences, expenses, rates, year, as_of, tfr_factor)
    annual = annual_summary([e for e in entries if e.work_date <= th["cutoff"]], [a for a in absences if a.start_date <= th["cutoff"]], [x for x in expenses if x.expense_date <= th["cutoff"]], rates, year, tfr_factor)
    inps = inps_contribution_summary(worker, annual, year)
    taxes = estimated_irpef_summary(worker, annual, year) if worker.inps_number and worker.contract_number else None
    return {"cutoff": th["cutoff"], "thirteenth": th, "tfr": tfr, "annual": annual, "inps": inps, "taxes": taxes}
