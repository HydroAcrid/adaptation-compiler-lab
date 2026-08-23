"""Render deterministic PNG documentation captures from reviewed terminal snapshots.

Run with an ephemeral Pillow dependency so the product dependency set stays unchanged:

    uv run --with pillow python scripts/render_terminal_gallery.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).parents[1]
SNAPSHOTS = ROOT / "tests" / "snapshots" / "terminal_alpha"
OUTPUT = ROOT / "docs" / "images" / "temper-terminal"
FONT_PATH = Path("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf")

CAPTURES = (
    ("status.txt", "Temper — Everyday Home", "temper-consumer-dashboard.png"),
    ("review.txt", "Temper — Suggestions", "temper-review-example.png"),
    ("adaptations.txt", "Temper — Active Adaptations", "temper-adaptation-example.png"),
    ("phone-status.txt", "Temper — Phone-Friendly Output", "temper-phone-output.png"),
)


def _render(source: Path, *, title: str, destination: Path) -> None:
    lines = source.read_text(encoding="utf-8").rstrip().splitlines()
    font = ImageFont.truetype(str(FONT_PATH), 20)
    title_font = ImageFont.truetype(str(FONT_PATH), 18)
    probe = Image.new("RGB", (1, 1))
    probe_draw = ImageDraw.Draw(probe)
    widths = [probe_draw.textlength(line, font=font) for line in lines]
    line_height = 27
    margin = 15
    chrome_height = 52
    width = max(720, int(max(widths, default=0)) + margin * 2)
    height = chrome_height + line_height * len(lines) + margin
    image = Image.new("RGB", (width, height), "#262626")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(
        (0, 0, width - 1, height - 1),
        radius=10,
        outline="#d0d7de",
        width=2,
    )
    for index, color in enumerate(("#ff5f57", "#febc2e", "#28c840")):
        left = 20 + index * 22
        draw.ellipse((left, 16, left + 13, 29), fill=color)
    title_box = draw.textbbox((0, 0), title, font=title_font)
    title_width = title_box[2] - title_box[0]
    draw.text(((width - title_width) / 2, 10), title, font=title_font, fill="#dbe8f5")
    for index, line in enumerate(lines):
        color = "#bfe8ff" if "Temper" in line else "#dbe8f5"
        draw.text((margin, chrome_height + index * line_height), line, font=font, fill=color)
    destination.parent.mkdir(parents=True, exist_ok=True)
    image.save(destination, format="PNG", optimize=True)


def main() -> None:
    for source_name, title, destination_name in CAPTURES:
        _render(
            SNAPSHOTS / source_name,
            title=title,
            destination=OUTPUT / destination_name,
        )


if __name__ == "__main__":
    main()
