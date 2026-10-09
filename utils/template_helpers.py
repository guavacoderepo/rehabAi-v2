"""Jinja filters and global helpers."""

import platform
from datetime import date, datetime

from services.bands import band_info


_DAY = "%#d" if platform.system() == "Windows" else "%-d"


def _to_date(value):
    if value is None or value == "":
        return None

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    return date.fromisoformat(str(value)[:10])


def age(dob):
    dob = _to_date(dob)

    if dob is None:
        return None

    today = date.today()

    return (
        today.year
        - dob.year
        - ((today.month, today.day) < (dob.month, dob.day))
    )


def longdate(value):
    d = _to_date(value)
    return d.strftime(f"{_DAY} %B %Y") if d else "—"


def shortdate(value):
    d = _to_date(value)
    return d.strftime("%d %b") if d else "—"


def ago(value):
    d = _to_date(value)

    if d is None:
        return "—"

    days = (date.today() - d).days

    if days <= 0:
        return "today"
    if days == 1:
        return "yesterday"
    if days < 7:
        return f"{days} days ago"
    if days < 14:
        return "a week ago"

    return f"{round(days / 7)} weeks ago"


def initials(name):
    return "".join(word[0] for word in str(name or "").split()[:2]).upper()


def tint(code):
    return "t" + str(sum(ord(c) for c in str(code)) % 4)


def signed(n):
    if n is None:
        return "—"
    if n > 0:
        return f"+{n:.1f}"
    if n == 0:
        return "±0"
    return f"{n:.1f}"


def gender_label(code):
    return {"F": "Female", "M": "Male", "X": "Other"}.get(code, "—")


def _greeting():
    hour = datetime.now().hour

    if hour < 12:
        return "Good morning"
    if hour < 18:
        return "Good afternoon"
    return "Good evening"


def register_template_helpers(app):
    for name, fn in {
        "age": age,
        "longdate": longdate,
        "shortdate": shortdate,
        "ago": ago,
        "initials": initials,
        "tint": tint,
        "signed": signed,
        "gender": gender_label,
    }.items():
        app.add_template_filter(fn, name)

    @app.context_processor
    def inject_helpers():
        return {
            "band_info": band_info,
            "greeting": _greeting(),
            "today_long": datetime.now().strftime(f"%A, {_DAY} %B"),
            "today_iso": date.today().isoformat(),
        }
