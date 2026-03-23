"""
Badge template renderer using Pillow.

Generates a standard badge image (3.375" x 2.125" at 300 DPI)
that can be printed directly or used as a fallback when Gutenberg
is unavailable.

+----------------------------------+
|  COMPANY NAME                    |
|  ==============================  |
|                                  |
|         JANE DOE                 |
|      Engineering                 |
|      ID: EMP-0042               |
|                                  |
|      2026-03-23  14:30           |
|  ==============================  |
|         VISITOR BADGE            |
+----------------------------------+
"""

import os
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# Badge dimensions: 3.375" x 2.125" at 300 DPI
BADGE_WIDTH = 1013
BADGE_HEIGHT = 638
DPI = 300

# Colors
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
PRIMARY = (33, 37, 41)       # Dark gray for text
ACCENT = (0, 86, 179)        # Blue accent
LIGHT_GRAY = (240, 240, 240)
BORDER = (200, 200, 200)

# Company name (override via environment variable)
COMPANY_NAME = os.environ.get("BADGE_COMPANY_NAME", "YOUR COMPANY")


def _get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Get a font, falling back to default if custom fonts aren't available."""
    # Try common system fonts
    font_names = (
        ["DejaVuSans-Bold.ttf", "arial-bold.ttf"] if bold
        else ["DejaVuSans.ttf", "arial.ttf"]
    )

    font_dirs = [
        "/usr/share/fonts/truetype/dejavu/",
        "/usr/share/fonts/TTF/",
        "C:/Windows/Fonts/",
        "/System/Library/Fonts/",
    ]

    for font_dir in font_dirs:
        for font_name in font_names:
            font_path = os.path.join(font_dir, font_name)
            if os.path.exists(font_path):
                return ImageFont.truetype(font_path, size)

    # Fallback to default
    try:
        return ImageFont.truetype("DejaVuSans.ttf", size)
    except (OSError, IOError):
        return ImageFont.load_default()


def render_badge(name: str, employee_id: str, department: str,
                 output_path: str, badge_type: str = "VISITOR BADGE") -> str:
    """Render a badge as a PNG image.

    Args:
        name: Person's full name.
        employee_id: Employee ID string.
        department: Department name.
        output_path: Where to save the PNG.
        badge_type: Label at the bottom (e.g., "VISITOR BADGE", "EMPLOYEE").

    Returns:
        The output path.
    """
    img = Image.new("RGB", (BADGE_WIDTH, BADGE_HEIGHT), WHITE)
    draw = ImageDraw.Draw(img)

    # Fonts
    font_company = _get_font(28, bold=True)
    font_name = _get_font(36, bold=True)
    font_detail = _get_font(22)
    font_badge_type = _get_font(18, bold=True)
    font_small = _get_font(16)

    # Border
    draw.rectangle(
        [0, 0, BADGE_WIDTH - 1, BADGE_HEIGHT - 1],
        outline=BORDER, width=2,
    )

    # Header bar
    draw.rectangle([0, 0, BADGE_WIDTH, 60], fill=ACCENT)
    _draw_centered_text(draw, COMPANY_NAME, 20, font_company, WHITE)

    # Separator line
    draw.line([(40, 80), (BADGE_WIDTH - 40, 80)], fill=LIGHT_GRAY, width=2)

    # Name (large, centered)
    _draw_centered_text(draw, name.upper(), 120, font_name, PRIMARY)

    # Department
    _draw_centered_text(draw, department, 175, font_detail, PRIMARY)

    # Employee ID
    _draw_centered_text(draw, f"ID: {employee_id}", 215, font_detail, PRIMARY)

    # Date and time
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M")
    _draw_centered_text(draw, f"{date_str}  {time_str}", 270, font_small, PRIMARY)

    # Bottom separator
    draw.line(
        [(40, BADGE_HEIGHT - 80), (BADGE_WIDTH - 40, BADGE_HEIGHT - 80)],
        fill=LIGHT_GRAY, width=2,
    )

    # Footer bar
    draw.rectangle(
        [0, BADGE_HEIGHT - 50, BADGE_WIDTH, BADGE_HEIGHT],
        fill=ACCENT,
    )
    _draw_centered_text(
        draw, badge_type, BADGE_HEIGHT - 35, font_badge_type, WHITE,
    )

    # Save
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path, "PNG", dpi=(DPI, DPI))

    return output_path


def _draw_centered_text(draw: ImageDraw.Draw, text: str, y: int,
                        font: ImageFont.FreeTypeFont, fill: tuple):
    """Draw text centered horizontally on the badge."""
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    x = (BADGE_WIDTH - text_width) // 2
    draw.text((x, y), text, font=font, fill=fill)


if __name__ == "__main__":
    # Quick test: render a sample badge
    output = render_badge(
        name="Jane Doe",
        employee_id="EMP-0042",
        department="Engineering",
        output_path="./output/sample_badge.png",
    )
    print(f"Sample badge saved to {output}")
