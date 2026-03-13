#!/usr/bin/env python3
"""
Generate schedule_options.xlsx with 3 schedule options (A, B, C).
Each option is a separate sheet containing all 4 shift sections.

Changes from original:
- No 12-hour shifts anywhere
- John Stenberg: weekday night supervisor (schedule unchanged)
- Noah Malloy: weekend afternoon supervisor (schedule unchanged)
- Lester Anderson: weekend night supervisor, 5x8 (was 2x12 + 2x8)
- Blaine Rapson: weekend morning supervisor, 5x8 (was 2x12 + 2x8)
- Ireland Van Wormer: weekends become 8hr (was 12hr)
- Michael Hoffman: Sat becomes 8hr (was 12hr)
"""

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

# Days of the week for headers
DAYS = ["Saturday 3/14", "Sunday 3/15", "Monday 3/16", "Tuesday 3/17",
        "Wednesday 3/18", "Thursday 3/19", "Friday 3/20"]
DAY_KEYS = ["Sat", "Sun", "Mon", "Tue", "Wed", "Thu", "Fri"]

# Styling
HEADER_FILL = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
HEADER_FONT = Font(bold=True, color="FFFFFF", size=11)
TITLE_FONT = Font(bold=True, italic=True, size=14)
NAME_FONT = Font(bold=True, size=10)
SUPV_FONT = Font(bold=True, size=10, color="0000AA")
NORMAL_FONT = Font(size=10)
OFF_FONT = Font(italic=True, size=10, color="888888")
CLEET_FONT = Font(bold=True, size=10, color="CC6600")
ORANGE_FILL = PatternFill(start_color="F4B084", end_color="F4B084", fill_type="solid")
LIGHT_BLUE_FILL = PatternFill(start_color="D6E4F0", end_color="D6E4F0", fill_type="solid")
THIN_BORDER = Border(
    left=Side(style="thin"), right=Side(style="thin"),
    top=Side(style="thin"), bottom=Side(style="thin")
)


def make_shift(start, end, hrs):
    """Create a shift dict."""
    return {"start": start, "end": end, "hrs": hrs}


def off():
    return {"start": "Off", "end": "Off", "hrs": 0}


def cleet():
    return {"start": "CLEET", "end": "CLEET", "hrs": 0}


def ro():
    return {"start": "R/O", "end": "R/O", "hrs": 0}


S8_13_21 = lambda: make_shift("13:00", "21:00", 8)
S8_21_5 = lambda: make_shift("21:00", "5:00", 8)
S8_5_13 = lambda: make_shift("5:00", "13:00", 8)
S8_3_11 = lambda: make_shift("3:00", "11:00", 8)
S8_11_19 = lambda: make_shift("11:00", "19:00", 8)
S8_5_13 = lambda: make_shift("5:00", "13:00", 8)


# ============================================================
# AFTERNOON SHIFT 13:00 - 21:00 (unchanged for all options)
# ============================================================
def get_afternoon_shift():
    return {
        "title": "Afternoon Shift 13:00 to 21:00",
        "staff": [
            {
                "name": "Dallas Box",
                "schedule": {
                    "Sat": off(), "Sun": off(),
                    "Mon": cleet(), "Tue": cleet(),
                    "Wed": cleet(), "Thu": cleet(), "Fri": cleet()
                }
            },
            {
                "name": "Nicholas Del Grosso",
                "note": "Faith Covering (Tue)",
                "schedule": {
                    "Sat": off(), "Sun": off(),
                    "Mon": S8_13_21(), "Tue": S8_13_21(),
                    "Wed": S8_13_21(), "Thu": S8_13_21(), "Fri": S8_13_21()
                }
            },
            {
                "name": "DJ Phillips",
                "schedule": {
                    "Sat": S8_13_21(), "Sun": off(),
                    "Mon": off(), "Tue": S8_13_21(),
                    "Wed": S8_13_21(), "Thu": S8_13_21(), "Fri": S8_13_21()
                }
            },
            {
                "name": "Noah Malloy (Wknd Supervisor)",
                "schedule": {
                    "Sat": S8_13_21(), "Sun": S8_13_21(),
                    "Mon": S8_13_21(), "Tue": off(),
                    "Wed": off(), "Thu": S8_13_21(), "Fri": S8_13_21()
                }
            },
            {
                "name": "Anthony Carter",
                "schedule": {
                    "Sat": S8_13_21(), "Sun": S8_13_21(),
                    "Mon": S8_13_21(), "Tue": S8_13_21(),
                    "Wed": S8_13_21(), "Thu": off(), "Fri": off()
                }
            },
            {
                "name": "Aniya Chatman",
                "schedule": {
                    "Sat": off(), "Sun": S8_13_21(),
                    "Mon": S8_13_21(), "Tue": S8_13_21(),
                    "Wed": S8_13_21(), "Thu": S8_13_21(), "Fri": off()
                }
            },
        ]
    }


# ============================================================
# SSD OFFICERS (unchanged for all options)
# ============================================================
def get_ssd_shift():
    return {
        "title": "SSD Officers",
        "staff": [
            {
                "name": "Open (Bobby Briggs)",
                "schedule": {
                    "Sat": S8_3_11(), "Sun": S8_3_11(),
                    "Mon": off(), "Tue": off(),
                    "Wed": off(), "Thu": off(), "Fri": off()
                }
            },
            {
                "name": "Open (Joshua Key / Faith Aston)",
                "schedule": {
                    "Sat": S8_11_19(), "Sun": S8_11_19(),
                    "Mon": off(), "Tue": off(),
                    "Wed": off(), "Thu": off(), "Fri": off()
                }
            },
            {
                "name": "Marcia Helms",
                "schedule": {
                    "Sat": off(), "Sun": off(),
                    "Mon": S8_11_19(), "Tue": S8_11_19(),
                    "Wed": S8_11_19(), "Thu": S8_11_19(), "Fri": S8_11_19()
                }
            },
            {
                "name": "Lesa Dougless",
                "schedule": {
                    "Sat": off(), "Sun": off(),
                    "Mon": S8_3_11(), "Tue": S8_3_11(),
                    "Wed": make_shift("11:00", "19:00", 8), "Thu": S8_3_11(),
                    "Fri": S8_3_11()
                }
            },
        ]
    }


# ============================================================
# NIGHT SHIFT 21:00 - 5:00 (varies by option for Lester, Ireland)
# ============================================================
def get_night_shift(option):
    """option is 'A', 'B', or 'C' determining Lester's 5th day."""

    # Lester's 5th day
    lester_sched = {
        "Sat": S8_21_5(), "Sun": S8_21_5(),
        "Mon": off(), "Tue": off(), "Wed": off(),
        "Thu": S8_21_5(), "Fri": S8_21_5()
    }
    if option == "A":
        lester_sched["Wed"] = S8_21_5()
    elif option == "B":
        lester_sched["Mon"] = S8_21_5()
    elif option == "C":
        lester_sched["Tue"] = S8_21_5()

    # Ireland Van Wormer - was 17-5 (12hr) on weekends, now 21-5 (8hr)
    ireland_sched = {
        "Sat": S8_21_5(), "Sun": S8_21_5(),
        "Mon": off(), "Tue": off(), "Wed": off(),
        "Thu": off(), "Fri": S8_21_5()
    }

    return {
        "title": "Night Shift 21:00 - 5:00",
        "staff": [
            {
                "name": "John Stenberg (Wkday Supervisor)",
                "schedule": {
                    "Sat": off(), "Sun": off(),
                    "Mon": S8_21_5(), "Tue": S8_21_5(),
                    "Wed": S8_21_5(), "Thu": S8_21_5(), "Fri": S8_21_5()
                }
            },
            {
                "name": "Lester Anderson (Wknd Supervisor)",
                "schedule": lester_sched
            },
            {
                "name": "Blake Poteet",
                "schedule": {
                    "Sat": S8_21_5(), "Sun": S8_21_5(),
                    "Mon": S8_21_5(), "Tue": S8_21_5(),
                    "Wed": off(), "Thu": off(), "Fri": off()
                }
            },
            {
                "name": "Connor Gibson",
                "note": "Joshua Key (Thu/Fri)",
                "schedule": {
                    "Sat": off(), "Sun": off(),
                    "Mon": off(), "Tue": S8_21_5(),
                    "Wed": S8_21_5(), "Thu": S8_21_5(), "Fri": ro()
                }
            },
            {
                "name": "Dyontre Walker",
                "note": "Ireland Covering (Fri)",
                "schedule": {
                    "Sat": S8_21_5(), "Sun": off(),
                    "Mon": off(), "Tue": off(),
                    "Wed": S8_21_5(), "Thu": S8_21_5(), "Fri": ro()
                }
            },
            {
                "name": "Jonathan Lawrence",
                "schedule": {
                    "Sat": S8_21_5(), "Sun": S8_21_5(),
                    "Mon": S8_21_5(), "Tue": off(),
                    "Wed": off(), "Thu": off(), "Fri": make_shift("22:00", "6:00", 8)
                }
            },
            {
                "name": "Tytina Fellows",
                "schedule": {
                    "Sat": off(), "Sun": off(),
                    "Mon": S8_21_5(), "Tue": S8_21_5(),
                    "Wed": S8_21_5(), "Thu": S8_21_5(), "Fri": off()
                }
            },
            {
                "name": "Ireland Van Wormer",
                "schedule": ireland_sched
            },
            {
                "name": "Eric Parks",
                "schedule": {
                    "Sat": off(), "Sun": S8_21_5(),
                    "Mon": S8_21_5(), "Tue": S8_21_5(),
                    "Wed": S8_21_5(), "Thu": off(), "Fri": off()
                }
            },
        ]
    }


# ============================================================
# MORNING SHIFT 5:00 - 13:00 (varies by option for Blaine, M. Hoffman)
# ============================================================
def get_morning_shift(option):
    """option is 'A', 'B', or 'C' determining Blaine's 5th day."""

    # Blaine's 5th day
    blaine_sched = {
        "Sat": S8_5_13(), "Sun": S8_5_13(),
        "Mon": off(), "Tue": off(), "Wed": off(),
        "Thu": S8_5_13(), "Fri": S8_5_13()
    }
    if option == "A":
        blaine_sched["Wed"] = S8_5_13()
    elif option == "B":
        blaine_sched["Mon"] = S8_5_13()
    elif option == "C":
        blaine_sched["Tue"] = S8_5_13()

    # Michael Hoffman - was 5-17 (12hr) on Sat, now 5-13 (8hr)
    hoffman_sched = {
        "Sat": S8_5_13(), "Sun": ro(),
        "Mon": off(), "Tue": off(), "Wed": off(),
        "Thu": off(), "Fri": off()
    }

    return {
        "title": "Morning Shift 5:00 - 13:00",
        "staff": [
            {
                "name": "Preston Fitzpatrick",
                "note": "Blaine Rapson (Fri)",
                "schedule": {
                    "Sat": off(), "Sun": off(),
                    "Mon": S8_5_13(), "Tue": S8_5_13(),
                    "Wed": S8_5_13(), "Thu": S8_5_13(), "Fri": ro()
                }
            },
            {
                "name": "Blaine Rapson (Wknd Supervisor)",
                "schedule": blaine_sched
            },
            {
                "name": "Chance Morgans",
                "schedule": {
                    "Sat": off(), "Sun": off(),
                    "Mon": S8_5_13(), "Tue": S8_5_13(),
                    "Wed": S8_5_13(), "Thu": S8_5_13(),
                    "Fri": make_shift("13:00", "21:00", 8)
                }
            },
            {
                "name": "Kolby Roberts",
                "schedule": {
                    "Sat": S8_5_13(), "Sun": S8_5_13(),
                    "Mon": S8_5_13(), "Tue": S8_5_13(),
                    "Wed": off(), "Thu": off(), "Fri": off()
                }
            },
            {
                "name": "Connor Hutchinson",
                "note": "Blaine Rapson (Wed), Jesse Carter (Thu)",
                "schedule": {
                    "Sat": S8_5_13(), "Sun": S8_5_13(),
                    "Mon": off(), "Tue": off(),
                    "Wed": off(), "Thu": off(), "Fri": S8_5_13()
                }
            },
            {
                "name": "Whitley Mayfield",
                "schedule": {
                    "Sat": off(), "Sun": off(),
                    "Mon": S8_5_13(), "Tue": S8_5_13(),
                    "Wed": S8_5_13(), "Thu": S8_5_13(), "Fri": S8_5_13()
                }
            },
            {
                "name": "Jesse Carter",
                "schedule": {
                    "Sat": S8_5_13(), "Sun": S8_5_13(),
                    "Mon": S8_5_13(), "Tue": S8_5_13(),
                    "Wed": S8_5_13(), "Thu": S8_5_13(), "Fri": S8_5_13()
                }
            },
            {
                "name": "Michael Hoffman",
                "note": "Joey Carnes (Sun)",
                "schedule": hoffman_sched
            },
        ]
    }


def write_section(ws, start_row, section_data):
    """Write one shift section to the worksheet starting at start_row.
    Returns the next available row."""

    row = start_row

    # --- Title row ---
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=22)
    cell = ws.cell(row=row, column=1, value=section_data["title"])
    cell.font = TITLE_FONT
    cell.alignment = Alignment(horizontal="center")
    row += 1

    # --- Header row: Name | Sat(start, end, hrs) | Sun(...) | ... | Fri(...) | Total ---
    headers = [""]
    for day_name in DAYS:
        headers.extend([day_name, "", ""])
    headers.append("Total")

    for col_idx, header in enumerate(headers, 1):
        cell = ws.cell(row=row, column=col_idx, value=header)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal="center")
        cell.border = THIN_BORDER

    # Merge day headers across 3 columns each
    for i in range(7):
        col_start = 2 + i * 3
        ws.merge_cells(start_row=row, start_column=col_start, end_row=row, end_column=col_start + 2)

    row += 1

    # --- Staff rows ---
    daily_counts = {d: 0 for d in DAY_KEYS}

    for person in section_data["staff"]:
        name = person["name"]
        sched = person["schedule"]
        is_supervisor = "Supervisor" in name

        # Name cell
        cell = ws.cell(row=row, column=1, value=name)
        cell.font = SUPV_FONT if is_supervisor else NAME_FONT
        cell.border = THIN_BORDER
        if is_supervisor:
            cell.fill = LIGHT_BLUE_FILL

        total_hrs = 0
        for day_idx, day_key in enumerate(DAY_KEYS):
            shift = sched[day_key]
            col_base = 2 + day_idx * 3

            start_val = shift["start"]
            end_val = shift["end"]
            hrs_val = shift["hrs"]
            total_hrs += hrs_val

            if hrs_val > 0:
                daily_counts[day_key] += 1

            # Start time
            c1 = ws.cell(row=row, column=col_base, value=start_val)
            # End time
            c2 = ws.cell(row=row, column=col_base + 1, value=end_val)
            # Hours
            c3 = ws.cell(row=row, column=col_base + 2, value=hrs_val if hrs_val > 0 else "")

            for c in (c1, c2, c3):
                c.border = THIN_BORDER
                c.alignment = Alignment(horizontal="center")
                if start_val in ("Off",):
                    c.font = OFF_FONT
                elif start_val in ("CLEET",):
                    c.font = CLEET_FONT
                elif start_val in ("R/O",):
                    c.font = Font(italic=True, bold=True, size=10)
                else:
                    c.font = NORMAL_FONT

        # Total column
        total_cell = ws.cell(row=row, column=23, value=total_hrs)
        total_cell.font = Font(bold=True, size=10)
        total_cell.border = THIN_BORDER
        total_cell.alignment = Alignment(horizontal="center")

        # Note row if applicable
        if "note" in person:
            row += 1
            note_cell = ws.cell(row=row, column=1, value="")
            for col_idx in range(1, 24):
                ws.cell(row=row, column=col_idx).border = THIN_BORDER
            # Put note in a visible spot
            note_c = ws.cell(row=row, column=5, value=person["note"])
            note_c.font = Font(italic=True, size=9, color="666666")

        row += 1

    # --- Blank separator row ---
    row += 1

    # --- Daily staffing count row ---
    ws.cell(row=row, column=1, value="Staff on duty").font = Font(bold=True, size=10)
    for day_idx, day_key in enumerate(DAY_KEYS):
        col_base = 2 + day_idx * 3
        count_cell = ws.cell(row=row, column=col_base, value=daily_counts[day_key])
        count_cell.font = Font(bold=True, size=11, color="FFFFFF")
        count_cell.fill = ORANGE_FILL
        count_cell.alignment = Alignment(horizontal="center")
        count_cell.border = THIN_BORDER
        ws.merge_cells(start_row=row, start_column=col_base, end_row=row, end_column=col_base + 2)

    row += 1

    # --- "Schedule is Subject to Change" row ---
    ws.merge_cells(start_row=row, start_column=6, end_row=row, end_column=16)
    note = ws.cell(row=row, column=6, value="Schedule is Subject to Change as Needed")
    note.font = Font(bold=True, size=9)
    note.alignment = Alignment(horizontal="center")
    note.border = THIN_BORDER

    row += 2  # Extra blank rows between sections
    return row


def create_option_sheet(wb, sheet_name, option_letter):
    """Create one option sheet with all 4 sections."""
    ws = wb.create_sheet(title=sheet_name)

    # Column widths
    ws.column_dimensions["A"].width = 32
    for i in range(2, 24):
        ws.column_dimensions[get_column_letter(i)].width = 7

    # Option label at top
    ws.merge_cells("A1:W1")
    title = ws.cell(row=1, column=1,
                    value=f"Schedule Option {option_letter} — "
                          f"Lester/Blaine extra day: "
                          f"{'Wednesday' if option_letter == 'A' else 'Monday' if option_letter == 'B' else 'Tuesday'}")
    title.font = Font(bold=True, size=16, color="003366")
    title.alignment = Alignment(horizontal="center")

    row = 3

    # Afternoon (same for all options)
    row = write_section(ws, row, get_afternoon_shift())

    # SSD (same for all options)
    row = write_section(ws, row, get_ssd_shift())

    # Night (varies)
    row = write_section(ws, row, get_night_shift(option_letter))

    # Morning (varies)
    row = write_section(ws, row, get_morning_shift(option_letter))


def main():
    wb = openpyxl.Workbook()
    # Remove default sheet
    wb.remove(wb.active)

    create_option_sheet(wb, "Option A - Wed", "A")
    create_option_sheet(wb, "Option B - Mon", "B")
    create_option_sheet(wb, "Option C - Tue", "C")

    output_path = "schedule_options.xlsx"
    wb.save(output_path)
    print(f"Generated {output_path} with 3 option sheets.")
    print()
    print("Key changes in all options:")
    print("  - John Stenberg: Weekday Night Supervisor (Mon-Fri 21-5, 40hrs)")
    print("  - Noah Malloy: Weekend Afternoon Supervisor (Sat,Sun,Mon,Thu,Fri 13-21, 40hrs)")
    print("  - Lester Anderson: Weekend Night Supervisor (5x8, 40hrs)")
    print("  - Blaine Rapson: Weekend Morning Supervisor (5x8, 40hrs)")
    print("  - Ireland Van Wormer: Weekends now 21-5 (8hr) instead of 17-5 (12hr)")
    print("  - Michael Hoffman: Sat now 5-13 (8hr) instead of 5-17 (12hr)")
    print("  - NO 12-hour shifts remain")
    print()
    print("Option A: Lester & Blaine add Wednesday")
    print("Option B: Lester & Blaine add Monday")
    print("Option C: Lester & Blaine add Tuesday")


if __name__ == "__main__":
    main()
