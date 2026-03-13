#!/usr/bin/env python3
"""
Conversational Excel Scheduler
===============================
Talk to this script in plain text and it builds/updates an Excel schedule.
The optimizer loops through shift assignments to ensure nobody works a 12-hour shift.

Usage:
    python3 scheduler.py                  # interactive mode (new schedule)
    python3 scheduler.py schedule.xlsx    # load existing schedule and keep editing

Example commands:
    "Add John, Sarah, Mike to the team"
    "John is available Monday through Friday 8am to 5pm"
    "Sarah can't work on Wednesday"
    "Mike prefers morning shifts"
    "We need 2 people covering 7am-3pm and 1 person covering 3pm-10pm every day"
    "Schedule next week"
    "Show the schedule"
    "Save as team_schedule.xlsx"
    "Optimize"
"""

import re
import sys
import copy
import random
import datetime
from collections import defaultdict
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

# ─── Constants ───────────────────────────────────────────────────────────────

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
DAY_ABBREV = {
    "mon": "Monday", "tue": "Tuesday", "tues": "Tuesday", "wed": "Wednesday",
    "thu": "Thursday", "thur": "Thursday", "thurs": "Thursday",
    "fri": "Friday", "sat": "Saturday", "sun": "Sunday",
    "monday": "Monday", "tuesday": "Tuesday", "wednesday": "Wednesday",
    "thursday": "Thursday", "friday": "Friday", "saturday": "Saturday",
    "sunday": "Sunday", "m": "Monday", "t": "Tuesday", "w": "Wednesday",
    "r": "Thursday", "f": "Friday",
}

MAX_SHIFT_HOURS = 11.99  # hard ceiling — 12h shifts are the enemy
IDEAL_SHIFT_HOURS = 8
MAX_WEEKLY_HOURS = 40
OPTIMIZATION_ITERATIONS = 500

# ─── Data Model ──────────────────────────────────────────────────────────────

class Person:
    def __init__(self, name: str):
        self.name = name
        # availability[day] = list of (start_hour, end_hour) windows  (24h float)
        self.availability: dict[str, list[tuple[float, float]]] = {d: [] for d in DAYS}
        self.preferences: list[str] = []  # "morning", "evening", etc.
        self.max_hours_per_week: float = MAX_WEEKLY_HOURS
        self.days_off: set[str] = set()

    def is_available(self, day: str, start: float, end: float) -> bool:
        if day in self.days_off:
            return False
        if not self.availability[day]:
            return False
        for a_start, a_end in self.availability[day]:
            if a_start <= start and a_end >= end:
                return True
        return False

    def __repr__(self):
        return f"Person({self.name})"


class Shift:
    def __init__(self, name: str, start: float, end: float, headcount: int = 1):
        self.name = name
        self.start = start  # 24h float, e.g. 7.0 = 7:00 AM
        self.end = end
        self.headcount = headcount  # how many people needed

    @property
    def duration(self) -> float:
        if self.end > self.start:
            return self.end - self.start
        return (24 - self.start) + self.end  # overnight

    def __repr__(self):
        return f"Shift({self.name} {fmt_time(self.start)}-{fmt_time(self.end)} x{self.headcount})"


class Assignment:
    def __init__(self, person: Person, shift: Shift, day: str):
        self.person = person
        self.shift = shift
        self.day = day


class Schedule:
    def __init__(self):
        self.people: dict[str, Person] = {}
        self.shifts: list[Shift] = []
        self.week_start: datetime.date | None = None
        self.assignments: list[Assignment] = []

    def add_person(self, name: str) -> Person:
        key = name.strip().title()
        if key not in self.people:
            self.people[key] = Person(key)
        return self.people[key]

    def get_person(self, name: str) -> Person | None:
        key = name.strip().title()
        return self.people.get(key)

    def remove_person(self, name: str) -> bool:
        key = name.strip().title()
        if key in self.people:
            del self.people[key]
            self.assignments = [a for a in self.assignments if a.person.name != key]
            return True
        return False

    def add_shift(self, name: str, start: float, end: float, headcount: int = 1) -> Shift:
        s = Shift(name, start, end, headcount)
        self.shifts.append(s)
        return s

    def person_weekly_hours(self, person: Person) -> float:
        return sum(a.shift.duration for a in self.assignments if a.person is person)

    def person_day_hours(self, person: Person, day: str) -> float:
        return sum(a.shift.duration for a in self.assignments
                   if a.person is person and a.day == day)

    def clear_assignments(self):
        self.assignments.clear()


# ─── Time Helpers ────────────────────────────────────────────────────────────

def parse_time(text: str) -> float | None:
    """Parse a time string into a 24h float. Returns None on failure."""
    text = text.strip().lower().replace(".", ":").replace(" ", "")
    m = re.match(r"^(\d{1,2}):?(\d{2})?\s*(am|pm)?$", text)
    if not m:
        return None
    hour = int(m.group(1))
    minute = int(m.group(2) or 0)
    ampm = m.group(3)
    if ampm == "pm" and hour != 12:
        hour += 12
    elif ampm == "am" and hour == 12:
        hour = 0
    if hour > 23 or minute > 59:
        return None
    return hour + minute / 60.0


def fmt_time(h: float) -> str:
    """Format a 24h float as a readable time string."""
    hour = int(h)
    minute = int((h - hour) * 60)
    ampm = "AM" if hour < 12 else "PM"
    display_hour = hour % 12 or 12
    if minute:
        return f"{display_hour}:{minute:02d}{ampm}"
    return f"{display_hour}{ampm}"


def parse_day(text: str) -> str | None:
    return DAY_ABBREV.get(text.strip().lower())


def parse_day_range(text: str) -> list[str]:
    """Parse 'Monday through Friday', 'Mon-Fri', 'weekdays', 'weekends', etc."""
    t = text.strip().lower()
    if t in ("weekdays", "weekday", "work days", "workdays"):
        return DAYS[:5]
    if t in ("weekends", "weekend"):
        return DAYS[5:]
    if t in ("every day", "everyday", "all days", "all week"):
        return list(DAYS)

    # range: "monday through friday", "mon-fri", "mon to fri"
    range_match = re.match(
        r"(\w+)\s*(?:through|thru|to|-)\s*(\w+)", t
    )
    if range_match:
        d1 = parse_day(range_match.group(1))
        d2 = parse_day(range_match.group(2))
        if d1 and d2:
            i1, i2 = DAYS.index(d1), DAYS.index(d2)
            if i2 >= i1:
                return DAYS[i1:i2 + 1]
            return DAYS[i1:] + DAYS[:i2 + 1]

    # comma-separated: "Monday, Wednesday, Friday"
    parts = re.split(r"[,\s]+(?:and\s+)?", t)
    result = []
    for p in parts:
        d = parse_day(p.strip())
        if d:
            result.append(d)
    return result


def next_monday() -> datetime.date:
    today = datetime.date.today()
    days_ahead = 7 - today.weekday()  # Monday = 0
    if days_ahead == 7:
        days_ahead = 0
    return today + datetime.timedelta(days=days_ahead)


# ─── Optimizer ───────────────────────────────────────────────────────────────

def score_schedule(schedule: Schedule) -> float:
    """
    Lower is better. Penalizes:
    - 12h+ shifts (massive penalty)
    - Shifts longer than 8h (scaled penalty)
    - Uneven distribution of hours
    - Unfilled shift slots
    - Preference mismatches
    """
    penalty = 0.0

    # Per-person checks
    hours_per_person: dict[str, float] = defaultdict(float)
    for a in schedule.assignments:
        dur = a.shift.duration
        hours_per_person[a.person.name] += dur

        # HARD penalty: 12h shift
        if dur >= 12:
            penalty += 10000

        # Soft penalty: shifts over ideal
        if dur > IDEAL_SHIFT_HOURS:
            penalty += (dur - IDEAL_SHIFT_HOURS) ** 2 * 10

        # Preference penalty
        if "morning" in a.person.preferences and a.shift.start >= 12:
            penalty += 5
        if "evening" in a.person.preferences and a.shift.start < 12:
            penalty += 5
        if "night" in a.person.preferences and a.shift.start < 17:
            penalty += 5

    # Weekly hours cap
    for name, hrs in hours_per_person.items():
        person = schedule.people[name]
        if hrs > person.max_hours_per_week:
            penalty += (hrs - person.max_hours_per_week) ** 2 * 5

    # Fairness: std-dev of weekly hours
    if hours_per_person:
        vals = list(hours_per_person.values())
        mean_h = sum(vals) / len(vals)
        variance = sum((v - mean_h) ** 2 for v in vals) / len(vals)
        penalty += variance * 2

    # Unfilled slots
    for day in DAYS:
        for shift in schedule.shifts:
            filled = sum(1 for a in schedule.assignments
                         if a.day == day and a.shift is shift)
            gap = shift.headcount - filled
            if gap > 0:
                penalty += gap * 500

    return penalty


def optimize(schedule: Schedule, iterations: int = OPTIMIZATION_ITERATIONS) -> str:
    """
    Loop through random valid assignments, keep the best scoring one.
    Returns a summary string.
    """
    if not schedule.people or not schedule.shifts:
        return "Need at least one person and one shift defined before optimizing."

    people_list = list(schedule.people.values())

    # Give everyone default full availability if none was set
    for p in people_list:
        for d in DAYS:
            if not p.availability[d] and d not in p.days_off:
                p.availability[d] = [(0, 24)]

    best_assignments: list[Assignment] = []
    best_score = float("inf")

    for iteration in range(iterations):
        candidate: list[Assignment] = []

        for day in DAYS:
            for shift in schedule.shifts:
                eligible = [
                    p for p in people_list
                    if p.is_available(day, shift.start, shift.end)
                ]
                random.shuffle(eligible)

                assigned_count = 0
                for p in eligible:
                    if assigned_count >= shift.headcount:
                        break

                    # Check daily hours cap (no 12h days)
                    day_hours = sum(
                        a.shift.duration for a in candidate
                        if a.person is p and a.day == day
                    )
                    if day_hours + shift.duration > MAX_SHIFT_HOURS:
                        continue

                    # Check weekly hours
                    week_hours = sum(
                        a.shift.duration for a in candidate if a.person is p
                    )
                    if week_hours + shift.duration > p.max_hours_per_week:
                        continue

                    candidate.append(Assignment(p, shift, day))
                    assigned_count += 1

        # Score this candidate
        temp = Schedule()
        temp.people = schedule.people
        temp.shifts = schedule.shifts
        temp.assignments = candidate
        s = score_schedule(temp)

        if s < best_score:
            best_score = s
            best_assignments = candidate

    schedule.assignments = best_assignments

    # Build summary
    total_slots = sum(s.headcount for s in schedule.shifts) * len(DAYS)
    filled = len(schedule.assignments)
    max_day_per_person: dict[str, float] = defaultdict(float)
    for a in schedule.assignments:
        key = (a.person.name, a.day)
        max_day_per_person[key] = max_day_per_person.get(key, 0) + a.shift.duration

    longest_day = max(max_day_per_person.values()) if max_day_per_person else 0
    has_12h = any(v >= 12 for v in max_day_per_person.values())

    lines = [
        f"Optimization complete ({iterations} iterations).",
        f"  Score: {best_score:.1f} (lower is better)",
        f"  Slots filled: {filled}/{total_slots}",
        f"  Longest single-day hours: {longest_day:.1f}h",
        f"  Any 12h+ shifts: {'YES — could not avoid' if has_12h else 'NONE — goal met!'}",
    ]

    # Per-person summary
    lines.append("\n  Weekly hours breakdown:")
    for p in sorted(schedule.people.values(), key=lambda x: x.name):
        wh = sum(a.shift.duration for a in schedule.assignments if a.person is p)
        lines.append(f"    {p.name}: {wh:.1f}h")

    return "\n".join(lines)


# ─── Excel I/O ───────────────────────────────────────────────────────────────

HEADER_FILL = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
HEADER_FONT = Font(bold=True, color="FFFFFF", size=11)
SHIFT_FILLS = [
    PatternFill(start_color="D6EAF8", end_color="D6EAF8", fill_type="solid"),
    PatternFill(start_color="D5F5E3", end_color="D5F5E3", fill_type="solid"),
    PatternFill(start_color="FDEBD0", end_color="FDEBD0", fill_type="solid"),
    PatternFill(start_color="F5B7B1", end_color="F5B7B1", fill_type="solid"),
    PatternFill(start_color="D7BDE2", end_color="D7BDE2", fill_type="solid"),
]
THIN_BORDER = Border(
    left=Side(style="thin"), right=Side(style="thin"),
    top=Side(style="thin"), bottom=Side(style="thin"),
)


def save_to_excel(schedule: Schedule, path: str):
    wb = Workbook()
    ws = wb.active
    ws.title = "Schedule"

    week_label = ""
    if schedule.week_start:
        end = schedule.week_start + datetime.timedelta(days=6)
        week_label = f"Week of {schedule.week_start.strftime('%b %d')} - {end.strftime('%b %d, %Y')}"

    # ── Title row ──
    ws.merge_cells("A1:H1")
    title_cell = ws["A1"]
    title_cell.value = week_label or "Weekly Schedule"
    title_cell.font = Font(bold=True, size=14, color="1F4E79")
    title_cell.alignment = Alignment(horizontal="center")

    # ── Headers: col A = Shift, cols B-H = Mon-Sun ──
    headers = ["Shift"] + DAYS
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=3, column=col, value=h)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal="center")
        cell.border = THIN_BORDER

    # ── Body rows: one row per shift ──
    row = 4
    for si, shift in enumerate(schedule.shifts):
        label = f"{shift.name}\n{fmt_time(shift.start)}-{fmt_time(shift.end)}"
        cell = ws.cell(row=row, column=1, value=label)
        cell.font = Font(bold=True, size=10)
        cell.alignment = Alignment(wrap_text=True, vertical="center")
        cell.border = THIN_BORDER
        fill = SHIFT_FILLS[si % len(SHIFT_FILLS)]

        for di, day in enumerate(DAYS):
            people_on = [
                a.person.name for a in schedule.assignments
                if a.day == day and a.shift is shift
            ]
            cell = ws.cell(row=row, column=di + 2, value="\n".join(people_on) if people_on else "—")
            cell.fill = fill
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            cell.border = THIN_BORDER

        row += 1

    # ── Summary section ──
    row += 1
    ws.cell(row=row, column=1, value="Hours Summary").font = Font(bold=True, size=12, color="1F4E79")
    row += 1
    summary_headers = ["Person", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun", "Total"]
    for col, h in enumerate(summary_headers, 1):
        cell = ws.cell(row=row, column=col, value=h)
        cell.font = Font(bold=True)
        cell.border = THIN_BORDER
    row += 1

    for p in sorted(schedule.people.values(), key=lambda x: x.name):
        ws.cell(row=row, column=1, value=p.name).border = THIN_BORDER
        total = 0.0
        for di, day in enumerate(DAYS):
            hrs = sum(a.shift.duration for a in schedule.assignments
                      if a.person is p and a.day == day)
            total += hrs
            cell = ws.cell(row=row, column=di + 2, value=hrs if hrs else "")
            cell.border = THIN_BORDER
            cell.alignment = Alignment(horizontal="center")
            if hrs >= 12:
                cell.font = Font(bold=True, color="FF0000")
        cell = ws.cell(row=row, column=9, value=total)
        cell.border = THIN_BORDER
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal="center")
        row += 1

    # Column widths
    ws.column_dimensions["A"].width = 20
    for col_letter in "BCDEFGH":
        ws.column_dimensions[col_letter].width = 16
    ws.column_dimensions["I"].width = 10

    # ── People sheet (roster + availability) ──
    ws2 = wb.create_sheet("Roster")
    ws2.cell(row=1, column=1, value="Name").font = Font(bold=True)
    ws2.cell(row=1, column=2, value="Preferences").font = Font(bold=True)
    ws2.cell(row=1, column=3, value="Days Off").font = Font(bold=True)
    ws2.cell(row=1, column=4, value="Max Hrs/Week").font = Font(bold=True)
    for ri, p in enumerate(sorted(schedule.people.values(), key=lambda x: x.name), 2):
        ws2.cell(row=ri, column=1, value=p.name)
        ws2.cell(row=ri, column=2, value=", ".join(p.preferences) if p.preferences else "")
        ws2.cell(row=ri, column=3, value=", ".join(sorted(p.days_off)) if p.days_off else "")
        ws2.cell(row=ri, column=4, value=p.max_hours_per_week)

    wb.save(path)


def load_from_excel(path: str) -> Schedule:
    """Load a previously saved schedule back in."""
    schedule = Schedule()
    wb = load_workbook(path)

    # Load roster
    if "Roster" in wb.sheetnames:
        ws2 = wb["Roster"]
        for row in ws2.iter_rows(min_row=2, values_only=True):
            if not row[0]:
                continue
            p = schedule.add_person(str(row[0]))
            if row[1]:
                p.preferences = [x.strip() for x in str(row[1]).split(",") if x.strip()]
            if row[2]:
                for d in str(row[2]).split(","):
                    d = d.strip()
                    if d in DAYS:
                        p.days_off.add(d)
            if row[3]:
                p.max_hours_per_week = float(row[3])

    # Load shifts from Schedule sheet
    ws = wb["Schedule"]
    # Row 3 = headers, row 4+ = shifts
    for row in ws.iter_rows(min_row=4, max_col=1, values_only=True):
        if not row[0] or row[0] == "Hours Summary":
            break
        label = str(row[0])
        # parse "Shift Name\n7AM-3PM"
        parts = label.split("\n")
        name = parts[0].strip()
        if len(parts) > 1:
            time_range = parts[1].strip()
            times = re.split(r"[-–]", time_range)
            if len(times) == 2:
                s = parse_time(times[0])
                e = parse_time(times[1])
                if s is not None and e is not None:
                    schedule.add_shift(name, s, e)

    return schedule


# ─── NLP Parser ──────────────────────────────────────────────────────────────

class ConversationEngine:
    def __init__(self, schedule: Schedule):
        self.schedule = schedule
        self.filepath = "schedule.xlsx"

    def process(self, text: str) -> str:
        """Parse plain-text input and return a human-readable response."""
        t = text.strip()
        if not t:
            return ""
        low = t.lower()

        # ── Save ──
        save_match = re.search(r"save\s+(?:as\s+|to\s+)?([^\s]+\.xlsx)", low)
        if save_match or low in ("save", "save it", "export"):
            if save_match:
                self.filepath = save_match.group(1)
            save_to_excel(self.schedule, self.filepath)
            return f"Saved to {self.filepath}"

        # ── Load ──
        load_match = re.search(r"(?:load|open)\s+([^\s]+\.xlsx)", low)
        if load_match:
            path = load_match.group(1)
            if Path(path).exists():
                self.schedule = load_from_excel(path)
                self.filepath = path
                return f"Loaded schedule from {path} ({len(self.schedule.people)} people, {len(self.schedule.shifts)} shifts)."
            return f"File not found: {path}"

        # ── Show / Print schedule ──
        if any(kw in low for kw in ("show", "print", "display", "view", "list schedule")):
            return self._show_schedule()

        # ── Optimize ──
        if any(kw in low for kw in ("optimize", "optimise", "generate", "auto", "schedule it",
                                     "fill it", "make the schedule", "create schedule",
                                     "build schedule", "assign everyone")):
            iters = OPTIMIZATION_ITERATIONS
            m = re.search(r"(\d+)\s*(?:iterations|iters|times|rounds)", low)
            if m:
                iters = min(int(m.group(1)), 5000)
            result = optimize(self.schedule, iters)
            save_to_excel(self.schedule, self.filepath)
            return result + f"\n\nAuto-saved to {self.filepath}"

        # ── Clear assignments ──
        if any(kw in low for kw in ("clear assignments", "reset assignments", "start over",
                                     "clear schedule", "reset schedule")):
            self.schedule.clear_assignments()
            return "All assignments cleared. People and shifts are still defined."

        # ── Remove person ──
        remove_match = re.match(r"(?:remove|delete|drop)\s+(\w[\w\s]*?)(?:\s+from.*)?$", low)
        if remove_match:
            name = remove_match.group(1).strip().title()
            if self.schedule.remove_person(name):
                return f"Removed {name} from the team."
            return f"Couldn't find anyone named {name}."

        # ── Availability (MUST come before shift and add-people) ──
        # "John is available Mon-Fri 8am to 5pm"
        # "Sarah works Monday through Friday 7am to 5pm"
        # "Mike can work Mon-Fri 8am to 10pm"
        avail_match = re.search(
            r"(\w+)\s+(?:is\s+)?(?:available|works?|can work)\s+"
            r"([\w\s,\-–]+?)\s+"
            r"(\d{1,2}(?::\d{2})?\s*(?:am|pm))\s*(?:to|-|–)\s*(\d{1,2}(?::\d{2})?\s*(?:am|pm))",
            low
        )
        if avail_match:
            name = avail_match.group(1).strip().title()
            days_text = avail_match.group(2).strip()
            start = parse_time(avail_match.group(3))
            end = parse_time(avail_match.group(4))
            days = parse_day_range(days_text)

            if start is not None and end is not None and days:
                p = self.schedule.add_person(name)
                for d in days:
                    p.availability[d] = [(start, end)]
                return f"{p.name} is available {', '.join(days)} from {fmt_time(start)} to {fmt_time(end)}."

        # ── Day off (before add-people) ──
        # "Sarah can't work Wednesday" / "Sarah has Wednesday off"
        off_match = re.search(
            r"(\w+)\s+(?:can'?t work|is off|has off|is unavailable|not available|off)\s*(?:on\s+)?([\w\s,\-–]+)",
            low
        )
        if not off_match:
            off_match = re.search(r"(\w+)\s+has\s+([\w\s,\-–]+?)\s+off", low)
        if off_match:
            name = off_match.group(1).strip().title()
            days = parse_day_range(off_match.group(2).strip())
            if days:
                p = self.schedule.add_person(name)
                p.days_off.update(days)
                return f"{p.name} now has {', '.join(days)} off."

        # ── Preferences (before add-people) ──
        # "Mike prefers mornings"
        pref_match = re.search(r"(\w+)\s+(?:prefers?|likes?|wants?)\s+(morning|evening|night|afternoon|early|late)", low)
        if pref_match:
            name = pref_match.group(1).strip().title()
            pref = pref_match.group(2).strip()
            p = self.schedule.add_person(name)
            if pref not in p.preferences:
                p.preferences.append(pref)
            return f"Noted: {p.name} prefers {pref} shifts."

        # ── Max hours (before add-people) ──
        # "John can only work 30 hours" / "Tom max 35 hours"
        hrs_match = re.search(r"(\w+)\s+(?:can only work|max|maximum|limit)\s+(\d+)\s*(?:hours|hrs|h)?", low)
        if hrs_match:
            name = hrs_match.group(1).strip().title()
            hrs = float(hrs_match.group(2))
            p = self.schedule.add_person(name)
            p.max_hours_per_week = hrs
            return f"{p.name} max weekly hours set to {hrs:.0f}h."

        # ── Define shifts ──
        # "Add a shift from 7am to 3pm with 2 people"
        # "Add a shift called Evening from 3pm to 10pm"
        # "We need 2 people from 7am to 3pm"
        shift_match = re.search(
            r"(?:add|create|define|need|want)\s+(?:a\s+)?shift\s+(?:called\s+|named\s+)?(\w+\s+)??"
            r"(?:from\s+|covering\s+)?(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)"
            r"\s*(?:to|-|–|through|thru)\s*"
            r"(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)"
            r"(?:\s*(?:with|needing|x|times)?\s*(\d+)\s*(?:people|person|staff|workers)?)?",
            low
        )
        if not shift_match:
            # Alt pattern: "we need 2 people from 7am to 3pm"
            shift_match = re.search(
                r"(?:need|want)\s+(\d+)\s+(?:people|person|staff|workers)\s+"
                r"(?:from\s+|covering\s+)?(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)"
                r"\s*(?:to|-|–|through|thru)\s*"
                r"(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)",
                low
            )
            if shift_match:
                # Rearrange groups: headcount is group 1, times are 2&3
                headcount = int(shift_match.group(1))
                start = parse_time(shift_match.group(2))
                end = parse_time(shift_match.group(3))
                if start is not None and end is not None:
                    name = self._auto_shift_name(start)
                    dur = (end - start) if end > start else (24 - start + end)
                    s = self.schedule.add_shift(name, start, end, headcount)
                    warn = ""
                    if dur >= 12:
                        warn = (f" — WARNING: this is a {dur:.1f}h shift! "
                                f"The optimizer will try to avoid assigning anyone a full 12h day. "
                                f"Consider splitting it into two shorter shifts.")
                    return f"Added shift '{s.name}' ({fmt_time(start)}-{fmt_time(end)}, {headcount} {'person' if headcount == 1 else 'people'}){warn}."
                shift_match = None  # reset so we fall through

        if shift_match:
            raw_name = (shift_match.group(1) or "").strip()
            start = parse_time(shift_match.group(2))
            end = parse_time(shift_match.group(3))
            headcount = int(shift_match.group(4) or 1)

            if start is not None and end is not None:
                skip_names = {"shift", "a shift", "from", "covering", ""}
                name = raw_name.title() if raw_name and raw_name.strip().lower() not in skip_names else self._auto_shift_name(start)

                dur = (end - start) if end > start else (24 - start + end)
                s = self.schedule.add_shift(name, start, end, headcount)
                warn = ""
                if dur >= 12:
                    warn = (f" — WARNING: this is a {dur:.1f}h shift! "
                            f"The optimizer will try to avoid assigning anyone a full 12h day. "
                            f"Consider splitting it into two shorter shifts.")
                return f"Added shift '{s.name}' ({fmt_time(start)}-{fmt_time(end)}, {headcount} {'person' if headcount == 1 else 'people'}){warn}."

        # ── Headcount update for existing shift ──
        hc_match = re.search(r"(?:need|want)\s+(\d+)\s+(?:people|person|staff)\s+(?:for|on|during)\s+(\w+)", low)
        if hc_match:
            count = int(hc_match.group(1))
            shift_name = hc_match.group(2).strip().title()
            for s in self.schedule.shifts:
                if shift_name.lower() in s.name.lower():
                    s.headcount = count
                    return f"Updated {s.name} to need {count} people."

        # ── Add people (MUST come after availability/shift/preference matchers) ──
        # "Add John, Sarah, Mike" or "Add John Sarah and Mike to the team"
        add_match = re.match(
            r"add\s+([\w\s,]+?)(?:\s+to\s+(?:the\s+)?(?:team|roster|schedule|staff))?$", low
        )
        if add_match:
            names_raw = add_match.group(1)
            names = re.split(r"[,\s]+(?:and\s+)?", names_raw)
            added = []
            for n in names:
                n = n.strip()
                if n and n not in ("and", "the", "to", "a", "shift"):
                    p = self.schedule.add_person(n)
                    added.append(p.name)
            if added:
                return f"Added: {', '.join(added)}. ({len(self.schedule.people)} people total)"
            return "Couldn't parse any names from that."

        # ── Schedule week: "schedule next week" ──
        if "next week" in low:
            self.schedule.week_start = next_monday()
            return f"Week set to start {self.schedule.week_start.strftime('%A, %b %d %Y')}."
        if "this week" in low:
            today = datetime.date.today()
            self.schedule.week_start = today - datetime.timedelta(days=today.weekday())
            return f"Week set to start {self.schedule.week_start.strftime('%A, %b %d %Y')}."

        # ── Status ──
        if any(kw in low for kw in ("status", "summary", "who", "how many", "roster", "team", "list people")):
            return self._status()

        # ── Help ──
        if any(kw in low for kw in ("help", "what can", "commands", "how do")):
            return HELP_TEXT

        return (
            f"I didn't fully understand that. Here's what I can do:\n{HELP_TEXT}\n"
            f"Tip: try 'help' for the full list."
        )

    def _auto_shift_name(self, start: float) -> str:
        if start < 6:
            base = "Overnight"
        elif start < 12:
            base = "Morning"
        elif start < 17:
            base = "Afternoon"
        else:
            base = "Evening"
        # Avoid duplicates
        existing = {s.name for s in self.schedule.shifts}
        name = base
        i = 2
        while name in existing:
            name = f"{base} {i}"
            i += 1
        return name

    def _show_schedule(self) -> str:
        if not self.schedule.assignments:
            return "No assignments yet. Define shifts and people, then say 'optimize' to generate the schedule."

        lines = ["Current Schedule:", "=" * 70]
        col_w = 14
        header = f"{'Shift':<20}" + "".join(f"{d:<{col_w}}" for d in DAYS)
        lines.append(header)
        lines.append("-" * 70)

        for shift in self.schedule.shifts:
            label = f"{shift.name} ({fmt_time(shift.start)}-{fmt_time(shift.end)})"
            row = f"{label:<20}"
            for day in DAYS:
                names = [a.person.name for a in self.schedule.assignments
                         if a.day == day and a.shift is shift]
                row += f"{', '.join(names) or '—':<{col_w}}"
            lines.append(row)

        lines.append("")
        lines.append("Hours per person:")
        for p in sorted(self.schedule.people.values(), key=lambda x: x.name):
            wh = sum(a.shift.duration for a in self.schedule.assignments if a.person is p)
            lines.append(f"  {p.name}: {wh:.1f}h")

        return "\n".join(lines)

    def _status(self) -> str:
        lines = [f"Team ({len(self.schedule.people)} people):"]
        for p in sorted(self.schedule.people.values(), key=lambda x: x.name):
            prefs = f" (prefers {', '.join(p.preferences)})" if p.preferences else ""
            off = f" (off: {', '.join(sorted(p.days_off))})" if p.days_off else ""
            lines.append(f"  - {p.name}{prefs}{off}")

        lines.append(f"\nShifts ({len(self.schedule.shifts)}):")
        for s in self.schedule.shifts:
            lines.append(f"  - {s.name}: {fmt_time(s.start)}-{fmt_time(s.end)} ({s.headcount} {'person' if s.headcount == 1 else 'people'})")

        if self.schedule.week_start:
            lines.append(f"\nWeek starts: {self.schedule.week_start.strftime('%A, %b %d %Y')}")

        lines.append(f"Assignments: {len(self.schedule.assignments)}")
        return "\n".join(lines)


HELP_TEXT = """
Commands you can type in plain English:

  PEOPLE
    "Add John, Sarah, Mike to the team"
    "Remove Mike"
    "John is available Monday through Friday 8am to 5pm"
    "Sarah can't work Wednesday"
    "Mike prefers morning shifts"
    "John max 30 hours"

  SHIFTS
    "Add a shift from 7am to 3pm with 2 people"
    "Add a shift called Evening from 3pm to 11pm"
    "Need 3 people for Morning"

  SCHEDULING
    "Schedule next week"
    "Optimize"  /  "Generate the schedule"
    "Optimize 1000 iterations"
    "Clear assignments" / "Start over"

  VIEW & EXPORT
    "Show the schedule"
    "Status"  /  "Roster"
    "Save"  /  "Save as my_schedule.xlsx"
    "Load schedule.xlsx"

  OTHER
    "Help"
    "Quit" / "Exit"

The optimizer runs hundreds of random schedules and picks the best one.
Its #1 goal: nobody works a 12-hour shift.
""".strip()


# ─── Main Loop ───────────────────────────────────────────────────────────────

def main():
    filepath = sys.argv[1] if len(sys.argv) > 1 else "schedule.xlsx"

    if Path(filepath).exists():
        print(f"Loading existing schedule from {filepath}...")
        schedule = load_from_excel(filepath)
        print(f"  Loaded {len(schedule.people)} people, {len(schedule.shifts)} shifts.")
    else:
        schedule = Schedule()

    engine = ConversationEngine(schedule)
    engine.filepath = filepath

    print()
    print("=" * 60)
    print("  CONVERSATIONAL EXCEL SCHEDULER")
    print("  Talk to me in plain English to build your schedule.")
    print("  Type 'help' for commands, 'quit' to exit.")
    print("=" * 60)
    print()

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "bye", "q"):
            save_to_excel(engine.schedule, engine.filepath)
            print(f"Schedule saved to {engine.filepath}. Goodbye!")
            break

        response = engine.process(user_input)
        print(f"\nScheduler: {response}\n")


if __name__ == "__main__":
    main()
