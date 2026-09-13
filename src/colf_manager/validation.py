from datetime import date, datetime
from decimal import Decimal, InvalidOperation


def parse_date(value, field):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field}: data non valida") from exc


def parse_time(value, field):
    try:
        return datetime.strptime(value, "%H:%M").time()
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field}: ora non valida") from exc


def nonnegative_decimal(value, field, default="0"):
    try:
        result = Decimal(str(value if value not in (None, "") else default))
    except InvalidOperation as exc:
        raise ValueError(f"{field}: numero non valido") from exc
    if result < 0:
        raise ValueError(f"{field}: deve essere >= 0")
    return result


def nonnegative_int(value, field, default=0):
    try:
        result = int(value if value not in (None, "") else default)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field}: intero non valido") from exc
    if result < 0:
        raise ValueError(f"{field}: deve essere >= 0")
    return result


def validate_work_times(start_time, end_time, break_minutes):
    today = date.today()
    start = datetime.combine(today, start_time)
    end = datetime.combine(today, end_time)
    if end <= start:
        raise ValueError("L'orario di fine deve essere successivo all'inizio")
    duration_minutes = int((end - start).total_seconds() // 60)
    if break_minutes >= duration_minutes:
        raise ValueError("La pausa deve essere inferiore alla durata del turno")


def validate_password(password):
    if len(password or "") < 12:
        raise ValueError("La password deve contenere almeno 12 caratteri")
    if not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password):
        raise ValueError("La password deve contenere lettere e numeri")
