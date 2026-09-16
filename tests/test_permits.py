from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from colf_manager.permit_rules import category_rule, personal_pool_hours, permit_metrics


def worker(**kwargs):
    base = dict(
        weekly_hours=40,
        live_in=False,
        live_in_reduced_schedule=False,
        union_officer=False,
        contract_type="permanent",
        employment_start=date(2024, 1, 1),
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


def absence(category, hours, paid=True, when=date(2026, 9, 10)):
    return SimpleNamespace(
        kind="permit",
        permit_category=category,
        paid=paid,
        paid_hours=Decimal(str(hours)),
        start_date=when,
    )


def test_personal_pool_live_in_and_non_live_in():
    assert personal_pool_hours(worker(live_in=True, weekly_hours=54)) == Decimal("16")
    reduced_live_in = worker(live_in=True, live_in_reduced_schedule=True, weekly_hours=30)
    assert personal_pool_hours(reduced_live_in) == Decimal("12")
    assert personal_pool_hours(worker(weekly_hours=40)) == Decimal("12")
    assert personal_pool_hours(worker(weekly_hours=20)) == Decimal("8")


def test_personal_categories_share_one_pool():
    w = worker(weekly_hours=40)
    metrics = permit_metrics(
        w,
        [absence("medical", 4), absence("residence_permit", 2)],
        2026,
        date(2026, 9, 15),
    )
    medical = next(x for x in metrics if x["category"] == "medical")
    residence = next(x for x in metrics if x["category"] == "residence_permit")
    assert medical["remaining"] == Decimal("6")
    assert residence["remaining"] == Decimal("6")


def test_training_rule_changes_seniority_from_november_2025():
    w = worker(employment_start=date(2025, 3, 1), weekly_hours=40)
    old = category_rule(w, "professional_training", date(2025, 10, 1))
    new = category_rule(w, "professional_training", date(2025, 11, 1))
    assert old["eligible"] is False
    assert new["eligible"] is True
    assert new["annual_total"] == Decimal("40")


def test_other_is_available_for_unpaid_tracking():
    w = worker()
    metrics = permit_metrics(w, [absence("other", 3, paid=False)], 2026, date(2026, 9, 15))
    other = next(x for x in metrics if x["category"] == "other")
    assert other["unpaid_year"] == Decimal("3")
    assert other["annual_total"] is None


def test_legacy_medical_visit_alias_is_aggregated():
    from datetime import date, time
    from decimal import Decimal
    from types import SimpleNamespace

    from colf_manager.permit_rules import permit_metrics

    worker = SimpleNamespace(
        weekly_hours=Decimal("40"),
        live_in=False,
        live_in_reduced_schedule=False,
        union_officer=False,
        employment_start=date(2025, 1, 1),
    )
    absence = SimpleNamespace(
        kind="permit",
        start_date=date(2026, 3, 2),
        end_date=date(2026, 3, 2),
        start_time=time(9),
        end_time=time(11),
        paid=True,
        permit_category="medical_visit",
        paid_beyond_legal_limit=False,
    )
    rows = permit_metrics(worker, [absence], 2026, date(2026, 9, 16))
    medical = next(row for row in rows if row["category"] == "medical")
    assert medical["paid_year"] == Decimal("2")
    assert medical["metric_category"] == "medical_visit"
