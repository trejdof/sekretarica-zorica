import json
import os
from datetime import date, datetime, timedelta

STATE_FILE = os.path.join(os.path.dirname(__file__), "state.json")

DEFAULT_STATE = {
    "day_start": "08:00",
    "base": 2,
    "interval_hours": 2.0,
    "consumed_today": 0,
    "last_reset_date": None,
}


def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return DEFAULT_STATE.copy()


def save_state(state: dict):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def _day_start_dt(state: dict, for_date: date = None) -> datetime:
    if for_date is None:
        for_date = date.today()
    h, m = map(int, state["day_start"].split(":"))
    return datetime(for_date.year, for_date.month, for_date.day, h, m)


def _maybe_reset(state: dict) -> dict:
    now = datetime.now()
    today_str = date.today().isoformat()
    if state.get("last_reset_date") != today_str and now >= _day_start_dt(state):
        state["consumed_today"] = 0
        state["last_reset_date"] = today_str
        save_state(state)
    return state


def get_status() -> dict:
    state = load_state()
    state = _maybe_reset(state)

    now = datetime.now()
    day_start_today = _day_start_dt(state)

    if now < day_start_today:
        return {
            "available": 0,
            "consumed": state["consumed_today"],
            "total_earned": 0,
            "day_started": False,
            "day_start_dt": day_start_today,
            "next_charge_dt": day_start_today,
            "interval_hours": state["interval_hours"],
            "base": state["base"],
            "day_start": state["day_start"],
        }

    hours_since = (now - day_start_today).total_seconds() / 3600
    charges_so_far = int(hours_since / state["interval_hours"])
    total_earned = state["base"] + charges_so_far
    available = max(0, total_earned - state["consumed_today"])

    next_charge_hours = (charges_so_far + 1) * state["interval_hours"]
    next_charge_dt = day_start_today + timedelta(hours=next_charge_hours)

    return {
        "available": available,
        "consumed": state["consumed_today"],
        "total_earned": total_earned,
        "day_started": True,
        "day_start_dt": day_start_today,
        "next_charge_dt": next_charge_dt,
        "interval_hours": state["interval_hours"],
        "base": state["base"],
        "day_start": state["day_start"],
    }


def smoke() -> tuple[bool, str | int]:
    state = load_state()
    state = _maybe_reset(state)
    status = get_status()

    if status["available"] <= 0:
        if not status["day_started"]:
            t = status["day_start_dt"].strftime("%H:%M")
            return False, f"Day hasn't started yet. First cigarette at {t}."
        t = status["next_charge_dt"].strftime("%H:%M")
        return False, f"No cigarettes available. Next one at {t}."

    state["consumed_today"] += 1
    save_state(state)
    return True, status["available"] - 1


def set_interval(hours: float) -> str:
    if hours <= 0:
        raise ValueError("Interval must be > 0")
    state = load_state()
    state["interval_hours"] = hours
    save_state(state)
    h = int(hours)
    m = int((hours - h) * 60)
    label = f"{h}h {m}m" if m else f"{h}h"
    return f"Charge interval set to every {label}."


def set_start(time_str: str) -> str:
    parts = time_str.split(":")
    if len(parts) != 2:
        raise ValueError("Use HH:MM format")
    h, m = int(parts[0]), int(parts[1])
    if not (0 <= h <= 23 and 0 <= m <= 59):
        raise ValueError("Invalid time")
    state = load_state()
    state["day_start"] = f"{h:02d}:{m:02d}"
    save_state(state)
    return f"Day start set to {h:02d}:{m:02d}."


def set_base(n: int) -> str:
    if n < 0:
        raise ValueError("Base must be >= 0")
    state = load_state()
    state["base"] = n
    save_state(state)
    return f"Base cigarettes set to {n}."


def format_status(status: dict) -> str:
    if not status["day_started"]:
        t = status["day_start_dt"].strftime("%H:%M")
        return f"Day hasn't started yet. First cigarette at {t}."

    available = status["available"]
    consumed = status["consumed"]
    total_earned = status["total_earned"]
    next_dt = status["next_charge_dt"]

    delta = next_dt - datetime.now()
    mins = max(0, int(delta.total_seconds() / 60))
    h, m = divmod(mins, 60)
    next_str = f"in {h}h {m}m" if h else f"in {m}m"

    bar_len = max(total_earned, 1)
    bar = "█" * consumed + "░" * (bar_len - consumed)

    return (
        f"🚬 Cigarettes today\n"
        f"Available: {available}  |  Smoked: {consumed}  |  Earned: {total_earned}\n"
        f"Next charge: {next_dt.strftime('%H:%M')} ({next_str})\n"
        f"Day resets at {status['day_start']} · interval: every {status['interval_hours']}h\n"
        f"[{bar}] {consumed}/{total_earned} smoked"
    )
