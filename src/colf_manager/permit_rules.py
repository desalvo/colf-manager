# fmt: off
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

PAID_PERMIT_CATEGORIES = {
    "medical": "Visite mediche documentate",
    "residence_permit": "Rinnovo permesso di soggiorno",
    "family_reunification": "Ricongiungimento familiare",
    "disability_family_care": "Assistenza familiare con grave disabilità certificata",
    "bereavement": "Lutto / comprovata disgrazia familiare",
    "childbirth_father": "Nascita di un figlio (padre)",
    "professional_training": "Formazione professionale",
    "professional_training_ebincolf": "Formazione riconosciuta/finanziata Ebincolf",
    "union": "Permesso sindacale",
}
UNPAID_ONLY_CATEGORIES = {"other": "Altro"}
PERMIT_CATEGORIES = {**PAID_PERMIT_CATEGORIES, **UNPAID_ONLY_CATEGORIES}
PERSONAL_POOL = {
    "medical",
    "residence_permit",
    "family_reunification",
    "disability_family_care",
}

PERMIT_CATEGORY_ALIASES = {
    "medical_visit": "medical",
}


def canonical_permit_category(value: str | None) -> str:
    category = (value or "other").strip()
    return PERMIT_CATEGORY_ALIASES.get(category, category)


def _d(value) -> Decimal:
    return Decimal(str(value or 0))


def daily_hours(worker) -> Decimal:
    """Gestionale conversion of a legal working day to hours for totals."""
    weekly = _d(getattr(worker, "weekly_hours", 0))
    return weekly / Decimal("6") if weekly > 0 else Decimal("0")


def personal_pool_hours(worker) -> Decimal:
    weekly = _d(getattr(worker, "weekly_hours", 0))
    if getattr(worker, "live_in", False):
        if getattr(worker, "live_in_reduced_schedule", False):
            return Decimal("12")
        return Decimal("16")
    if weekly >= Decimal("30"):
        return Decimal("12")
    return Decimal("12") * weekly / Decimal("30") if weekly > 0 else Decimal("0")


def training_eligibility(worker, as_of: date, ebincolf: bool = False) -> tuple[bool, Decimal, str]:
    # New CCNL from 2025-11-01 reduced seniority requirement from 12 to 6 months.
    required_months = 6 if as_of >= date(2025, 11, 1) else 12
    start = getattr(worker, "employment_start", None)
    if not start or as_of < start:
        return False, Decimal("0"), f"anzianità minima {required_months} mesi"
    months = (as_of.year - start.year) * 12 + (as_of.month - start.month)
    anniversary_reached = months > required_months or (
        months == required_months and as_of.day >= start.day
    )
    full_time_threshold = Decimal("54") if getattr(worker, "live_in", False) else Decimal("40")
    full_time = _d(getattr(worker, "weekly_hours", 0)) >= full_time_threshold
    permanent = getattr(worker, "contract_type", "permanent") == "permanent"
    eligible = anniversary_reached and full_time and permanent
    hours = Decimal("64" if ebincolf else "40") if eligible else Decimal("0")
    note = f"tempo pieno, indeterminato, anzianità minima {required_months} mesi"
    return eligible, hours, note


def category_rule(worker, category: str, as_of: date) -> dict:
    label = PERMIT_CATEGORIES.get(category, category or "Non classificato")
    if category in PERSONAL_POOL:
        total = personal_pool_hours(worker)
        if category == "disability_family_care" and as_of < date(2025, 11, 1):
            return {
                "label": label,
                "unit": "unlimited",
                "annual_total": None,
                "group": category,
                "basis": (
                    "CCNL previgente: assistenza familiare con disabilità fruibile "
                    "come permesso non retribuito previo accordo"
                ),
                "eligible": False,
            }
        return {
            "label": label,
            "unit": "hours",
            "annual_total": total,
            "group": "personal_pool",
            "basis": "Art. 19 CCNL - monte ore comune",
            "eligible": True,
        }
    if category == "bereavement":
        return {
            "label": label,
            "unit": "event",
            "event_days": Decimal("3"),
            "annual_total": None,
            "group": category,
            "basis": "Art. 19 CCNL - 3 giorni lavorativi per evento",
        }
    if category == "childbirth_father":
        if as_of >= date(2025, 11, 1):
            return {
                "label": label,
                "unit": "event",
                "event_days": Decimal("2"),
                "annual_total": None,
                "group": category,
                "basis": "Art. 19 CCNL 2025-2028 - 2 giorni per evento",
            }
        return {
            "label": label,
            "unit": "external",
            "annual_total": None,
            "group": category,
            "basis": "CCNL previgente: misura rinviata alla normativa vigente del periodo",
        }
    if category in {"professional_training", "professional_training_ebincolf"}:
        eligible, hours, note = training_eligibility(
            worker,
            as_of,
            category.endswith("ebincolf"),
        )
        return {
            "label": label,
            "unit": "hours",
            "annual_total": hours,
            "group": category,
            "basis": f"Art. 20 CCNL - {note}",
            "eligible": eligible,
        }
    if category == "union":
        eligible = bool(getattr(worker, "union_officer", False))
        days = Decimal("6") if eligible else Decimal("0")
        return {
            "label": label,
            "unit": "days",
            "annual_total": days,
            "group": category,
            "basis": "Art. 43 CCNL - componenti organismi direttivi sindacali",
            "eligible": eligible,
        }
    if category == "other":
        return {
            "label": label,
            "unit": "unlimited",
            "annual_total": None,
            "group": category,
            "basis": "Permesso non retribuito per giustificati motivi, previo accordo",
        }
    return {
        "label": label,
        "unit": "unknown",
        "annual_total": None,
        "group": category,
        "basis": "Categoria non riconosciuta",
    }


def absence_hours(absence) -> Decimal:
    paid_hours = _d(getattr(absence, "paid_hours", 0))
    if getattr(absence, "paid", False) and paid_hours > 0:
        return paid_hours
    start_time = getattr(absence, "start_time", None)
    end_time = getattr(absence, "end_time", None)
    start_date = getattr(absence, "start_date", None)
    end_date = getattr(absence, "end_date", start_date)
    if start_time and end_time and start_date:
        seconds = (
            datetime.combine(start_date, end_time) - datetime.combine(start_date, start_time)
        ).total_seconds()
        daily = Decimal(str(seconds)) / Decimal("3600")
        days = Decimal((end_date - start_date).days + 1) if end_date else Decimal("1")
        return max(Decimal("0"), daily * days)
    return paid_hours


def permit_metrics(worker, absences, year: int, as_of: date | None = None) -> list[dict]:
    cutoff = min(as_of or date.today(), date(year, 12, 31))
    period_start = date(year, 1, 1)
    categories = list(PAID_PERMIT_CATEGORIES) + ["other"]
    month_start = date(cutoff.year, cutoff.month, 1) if cutoff.year == year else date(year, 12, 1)
    result = []
    all_permits = [
        a
        for a in absences
        if getattr(a, "kind", None) == "permit" and a.start_date.year == year
    ]
    personal_paid_used = sum(
        (
            absence_hours(a)
            for a in all_permits
            if getattr(a, "paid", False)
            and canonical_permit_category(getattr(a, "permit_category", None)) in PERSONAL_POOL
            and a.start_date <= cutoff
        ),
        Decimal("0"),
    )
    pool_total = personal_pool_hours(worker)
    for category in categories:
        rule = category_rule(worker, category, cutoff)
        category_abs = [
            a
            for a in all_permits
            if canonical_permit_category(getattr(a, "permit_category", None)) == category
        ]
        paid_month = sum(
            (
                absence_hours(a)
                for a in category_abs
                if a.paid and month_start <= a.start_date <= cutoff
            ),
            Decimal("0"),
        )
        paid_year = sum(
            (
                absence_hours(a)
                for a in category_abs
                if a.paid and period_start <= a.start_date <= cutoff
            ),
            Decimal("0"),
        )
        unpaid_month = sum(
            (
                absence_hours(a)
                for a in category_abs
                if not a.paid and month_start <= a.start_date <= cutoff
            ),
            Decimal("0"),
        )
        unpaid_year = sum(
            (
                absence_hours(a)
                for a in category_abs
                if not a.paid and period_start <= a.start_date <= cutoff
            ),
            Decimal("0"),
        )
        annual = rule.get("annual_total")
        if rule.get("group") == "personal_pool":
            remaining = max(Decimal("0"), pool_total - personal_paid_used)
            employment_start = getattr(worker, "employment_start", period_start)
            accrued = pool_total if cutoff >= max(period_start, employment_start) else Decimal("0")
        elif isinstance(annual, Decimal):
            if rule.get("unit") == "days":
                annual_hours = annual * daily_hours(worker)
                remaining = max(Decimal("0"), annual_hours - paid_year)
                accrued = annual_hours
            else:
                remaining = max(Decimal("0"), annual - paid_year)
                accrued = annual
        else:
            remaining = None
            accrued = None
        extra_paid_month = sum(
            (
                absence_hours(a)
                for a in category_abs
                if a.paid
                and getattr(a, "paid_beyond_legal_limit", False)
                and month_start <= a.start_date <= cutoff
            ),
            Decimal("0"),
        )
        extra_paid_year = sum(
            (
                absence_hours(a)
                for a in category_abs
                if a.paid
                and getattr(a, "paid_beyond_legal_limit", False)
                and period_start <= a.start_date <= cutoff
            ),
            Decimal("0"),
        )
        result.append(
            {
                **rule,
                "category": category,
                "metric_category": "medical_visit" if category == "medical" else category,
                "paid_month": paid_month,
                "paid_year": paid_year,
                "unpaid_month": unpaid_month,
                "unpaid_year": unpaid_year,
                "extra_paid_month": extra_paid_month,
                "extra_paid_year": extra_paid_year,
                "accrued_to_date": accrued,
                "remaining": remaining,
            }
        )
    return result


def validate_paid_permit(worker, absences, candidate, replacing=None):
    if candidate.kind != "permit":
        return
    category = canonical_permit_category(getattr(candidate, "permit_category", None))
    if candidate.paid and category == "other":
        raise ValueError("La categoria 'Altro' è disponibile solo per permessi non retribuiti")
    if category not in PERMIT_CATEGORIES:
        raise ValueError("Categoria permesso non valida")
    if not candidate.paid:
        return
    employer_override = bool(getattr(candidate, "paid_beyond_legal_limit", False))
    rule = category_rule(worker, category, candidate.start_date)
    current = [
        a
        for a in absences
        if a.kind == "permit" and a.id != getattr(replacing, "id", None)
    ]
    if rule.get("eligible") is False and not employer_override:
        raise ValueError(
            "Permesso retribuito non spettante per questa categoria/data: "
            f"{rule['basis']}"
        )
    if category in PERSONAL_POOL:
        # A missing weekly schedule means the statutory pool cannot yet be
        # calculated reliably. Do not turn an unconfigured value into a zero
        # entitlement and block the record; the overview will still show that
        # the contractual schedule must be completed.
        if _d(getattr(worker, "weekly_hours", 0)) <= 0:
            return
        used = sum(
            (
                absence_hours(a)
                for a in current
                if a.paid
                and canonical_permit_category(getattr(a, "permit_category", None)) in PERSONAL_POOL
                and a.start_date.year == candidate.start_date.year
            ),
            Decimal("0"),
        )
        if (
            used + absence_hours(candidate) > personal_pool_hours(worker)
            and not employer_override
        ):
            raise ValueError(
                "Monte ore retribuito comune dei permessi ex art. 19 superato; "
                "abilita il trattamento di miglior favore del datore per retribuire oltre "
                "il limite"
            )
    elif category in {"professional_training", "professional_training_ebincolf"}:
        used = sum(
            (
                absence_hours(a)
                for a in current
                if a.paid
                and canonical_permit_category(getattr(a, "permit_category", None)) == category
                and a.start_date.year == candidate.start_date.year
            ),
            Decimal("0"),
        )
        total = rule.get("annual_total") or Decimal("0")
        if used + absence_hours(candidate) > total and not employer_override:
            raise ValueError(
                "Monte ore annuo per formazione superato; abilita il trattamento di "
                "miglior favore del datore"
            )
    elif category == "union":
        total_hours = (rule.get("annual_total") or Decimal("0")) * daily_hours(worker)
        used = sum(
            (
                absence_hours(a)
                for a in current
                if a.paid
                and canonical_permit_category(getattr(a, "permit_category", None)) == category
                and a.start_date.year == candidate.start_date.year
            ),
            Decimal("0"),
        )
        if used + absence_hours(candidate) > total_hours and not employer_override:
            raise ValueError(
                "Monte ore equivalente ai 6 giorni annui di permesso sindacale superato; "
                "abilita il trattamento di miglior favore del datore"
            )
    elif category in {"bereavement", "childbirth_father"} and rule.get("event_days"):
        max_hours = rule["event_days"] * daily_hours(worker)
        if (
            max_hours > 0
            and absence_hours(candidate) > max_hours
            and not employer_override
        ):
            raise ValueError(
                f"Il singolo evento supera il limite di {rule['event_days']} giorni "
                "lavorativi; abilita il trattamento di miglior favore del datore"
            )
