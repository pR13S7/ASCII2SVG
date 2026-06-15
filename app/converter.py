"""
Core conversion logic: ASCII art -> SVG, SVG -> PNG.

ascii_to_svg  — converts a plain-text ASCII diagram to an SVG string via svgbob
svg_to_png    — rasterises an SVG string to PNG bytes via cairosvg
"""

from __future__ import annotations

import logging
import os
import subprocess
from xml.sax.saxutils import escape

logger = logging.getLogger(__name__)

# B1 — build-verified binary name.  Confirm via `svgbob --help` in the Docker
# build; the binary produced by `cargo install svgbob_cli` is named `svgbob`.
# Adjust here AND in the Dockerfile COPY line if the actual name differs.
SVGBOB_BIN = os.environ.get("SVGBOB_BIN", "svgbob")


class ConversionError(ValueError):
    """Raised when a conversion step fails for a known reason."""


# ---------------------------------------------------------------------------
# Theme definitions — diagram colours (not page UI)
# ---------------------------------------------------------------------------

THEMES: dict[str, dict[str, str]] = {
    "light": {
        "background": "#ffffff",
        "foreground": "#1a1a1a",
        # Monospace preserves ASCII column alignment.
        # DejaVu Sans Mono is provided by fonts-dejavu-core (installed in Dockerfile).
        "font_family": "'DejaVu Sans Mono', Menlo, Consolas, monospace",
    },
    "dark": {
        "background": "#1e1e1e",
        "foreground": "#e6e6e6",
        # Monospace preserves ASCII column alignment.
        # DejaVu Sans Mono is provided by fonts-dejavu-core (installed in Dockerfile).
        "font_family": "'DejaVu Sans Mono', Menlo, Consolas, monospace",
    },
}

_DEFAULT_THEME = "light"

# Unicode-to-ASCII normalization for svgbob input.
# svgbob is optimized for ASCII diagrams; many users paste box-drawing Unicode.
_SVGBOB_NORMALIZE_MAP = str.maketrans(
    {
        "│": "|",
        "┃": "|",
        "┆": "|",
        "┇": "|",
        "╎": "|",
        "╏": "|",
        "─": "-",
        "━": "-",
        "┄": "-",
        "┅": "-",
        "┈": "-",
        "┉": "-",
        "╴": "-",
        "╶": "-",
        "┌": "+",
        "┐": "+",
        "└": "+",
        "┘": "+",
        "├": "+",
        "┤": "+",
        "┬": "+",
        "┴": "+",
        "┼": "+",
        "┏": "+",
        "┓": "+",
        "┗": "+",
        "┛": "+",
        "┣": "+",
        "┫": "+",
        "┳": "+",
        "┻": "+",
        "╋": "+",
        "╭": "+",
        "╮": "+",
        "╯": "+",
        "╰": "+",
        "►": ">",
        "▶": ">",
        "▸": ">",
        "→": ">",
        "⟶": ">",
        "➡": ">",
        "◄": "<",
        "◀": "<",
        "◂": "<",
        "←": "<",
        "▼": "v",
        "▽": "v",
        "↓": "v",
        "▲": "^",
        "△": "^",
        "↑": "^",
        "≤": "<=",
        "≥": ">=",
        "…": "...",
        "—": "-",
        "–": "-",
        "‑": "-",
        "🎉": "*",
    }
)


def _normalize_for_svgbob(text: str) -> str:
    """
    Normalize common Unicode diagram glyphs to ASCII so svgbob can parse them.

    This preserves user intent for box/arrow diagrams pasted from docs/chats.
    """
    normalized = text.translate(_SVGBOB_NORMALIZE_MAP)
    if normalized != text:
        logger.info("Normalized Unicode diagram glyphs to ASCII for svgbob parsing")
    return normalized


# ---------------------------------------------------------------------------
# Theme post-processing — applied to svgbob output regardless of CLI flags
# ---------------------------------------------------------------------------

def _apply_theme_to_svg(svg: str, theme_cfg: dict) -> str:
    """
    Make svgbob's output honour the selected theme.

    svgbob may emit built-in CSS that is tuned for a light theme and can produce
    visual artifacts (text overlap / reduced readability) when consumers apply
    a different font or colour context. To keep rendering stable across versions,
    inject an explicit, high-specificity override style block and an opaque
    background rect.
    """
    bg = theme_cfg["background"]
    fg = theme_cfg["foreground"]

    # Force stable stroke/fill/text rendering via targeted overrides, instead of
    # global "stroke: black" string replacement which can affect unrelated rules.
    style_override = (
        "<style>"
        ".svgbob line,.svgbob path,.svgbob circle,.svgbob rect,.svgbob polygon{"
        f"stroke:{fg}!important;"
        "}"
        ".svgbob text{"
        f"fill:{fg}!important;"
        "stroke:none!important;"
        f"font-family:{theme_cfg['font_family']}!important;"
        "}"
        ".svgbob .filled{"
        f"fill:{fg}!important;"
        "}"
        "</style>"
    )

    # Inject an opaque background rect right after the opening <svg ...> tag.
    # Locate "<svg" explicitly so a leading <?xml ...?> declaration is handled.
    rect = f'<rect width="100%" height="100%" fill="{bg}"/>'
    svg_start = svg.find("<svg")
    if svg_start == -1:
        return svg  # malformed — return as-is
    svg_tag_end = svg.find(">", svg_start)
    if svg_tag_end == -1:
        return svg  # malformed — return as-is
    return "\n".join(
        [
            svg[: svg_tag_end + 1],
            style_override,
            rect,
            svg[svg_tag_end + 1 :],
        ]
    )


# ---------------------------------------------------------------------------
# ASCII -> SVG  (via svgbob CLI)
# ---------------------------------------------------------------------------

def ascii_to_svg(text: str, theme: str = _DEFAULT_THEME) -> str:
    """
    Convert an ASCII-art diagram to SVG by shelling out to the svgbob binary.

    Input limits: ≤ 500 lines, ≤ 500 columns per line (consistent with routes).
    ``theme`` keys are resolved from THEMES; unknown values fall back to light.

    B1 note — svgbob CLI flag names must be confirmed via `svgbob --help` in
    the Docker build.  Documented-likely names used here:
      --background <hex>   background fill colour
      --fill-color <hex>   foreground / stroke fill colour
      --font-family <str>  font family for text elements
    Adjust flag names here if `svgbob --help` shows different names.
    """
    if not text or not text.strip():
        raise ConversionError("Input text is empty")

    normalized_text = _normalize_for_svgbob(text)

    lines = normalized_text.splitlines()
    if len(lines) > 500:
        raise ConversionError("Input exceeds 500 lines")

    max_cols = max((len(line) for line in lines), default=0)
    if max_cols > 500:
        raise ConversionError("Input exceeds 500 columns")

    # Resolve theme; unknown names fall back to light silently.
    theme_cfg = THEMES.get(theme)
    if theme_cfg is None:
        logger.warning("Unknown theme %r — falling back to %r", theme, _DEFAULT_THEME)
        theme_cfg = THEMES[_DEFAULT_THEME]

    bg = theme_cfg["background"]
    fg = theme_cfg["foreground"]
    font = theme_cfg["font_family"]

    # B1 — flag names are documented-likely; confirm via `svgbob --help`.
    cmd = [
        SVGBOB_BIN,
        "--background", bg,
        "--fill-color", fg,
        "--font-family", font,
    ]

    try:
        result = subprocess.run(
            cmd,
            input=normalized_text.encode("utf-8"),
            capture_output=True,
            timeout=10,
            shell=False,
        )
    except FileNotFoundError:
        raise ConversionError(
            "svgbob binary not found — ensure it is installed (SVGBOB_BIN env var)"
        )
    except subprocess.TimeoutExpired:
        raise ConversionError("svgbob conversion timed out")

    if result.returncode != 0 or not result.stdout:
        stderr_snippet = result.stderr.decode("utf-8", errors="replace")[:500]
        logger.error("svgbob failed (rc=%d): %s", result.returncode, stderr_snippet)
        raise ConversionError("Diagram conversion failed — check server logs for details")

    svg = result.stdout.decode("utf-8")

    # Post-process: guarantee theme colours regardless of whether CLI flags
    # took full effect (versions differ in which flags they honour).
    svg = _apply_theme_to_svg(svg, theme_cfg)

    return svg


# ---------------------------------------------------------------------------
# Plain text -> SVG  (verbatim monospace; no diagram interpretation)
# ---------------------------------------------------------------------------

_TEXT_CHAR_W = 8.5   # px advance per monospace column at the font size below
_TEXT_LINE_H = 19    # px per line
_TEXT_FONT_SIZE = 15
_TEXT_PAD = 12       # px padding around the text block


def text_to_svg(text: str, theme: str = _DEFAULT_THEME) -> str:
    """
    Render input verbatim as monospace SVG, WITHOUT svgbob's diagram parsing.

    Each line is emitted as one positioned <tspan>; the monospace font's own
    advance keeps Unicode box-drawing glyphs (│ ─ ┌ ┐ └ ┘ ├ ▼ ► ◄) connected and
    columns aligned. Use this for box-drawing diagrams, tables and prose; use
    ``ascii_to_svg`` only for hand-drawn ASCII art made of - | + / \\.
    """
    if not text or not text.strip():
        raise ConversionError("Input text is empty")

    lines = text.split("\n")
    if len(lines) > 500:
        raise ConversionError("Input exceeds 500 lines")

    max_cols = max((len(line) for line in lines), default=0)
    if max_cols > 500:
        raise ConversionError("Input exceeds 500 columns")

    theme_cfg = THEMES.get(theme)
    if theme_cfg is None:
        logger.warning("Unknown theme %r — falling back to %r", theme, _DEFAULT_THEME)
        theme_cfg = THEMES[_DEFAULT_THEME]

    bg = theme_cfg["background"]
    fg = theme_cfg["foreground"]
    font = theme_cfg["font_family"]

    width = int(max_cols * _TEXT_CHAR_W) + 2 * _TEXT_PAD
    height = len(lines) * _TEXT_LINE_H + 2 * _TEXT_PAD

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        f'<rect width="100%" height="100%" fill="{bg}"/>',
        f'<text xml:space="preserve" font-family="{font}" '
        f'font-size="{_TEXT_FONT_SIZE}" fill="{fg}">',
    ]
    for i, line in enumerate(lines):
        y = _TEXT_PAD + (i + 1) * _TEXT_LINE_H - 4
        parts.append(f'<tspan x="{_TEXT_PAD}" y="{y}">{escape(line)}</tspan>')
    parts.append("</text>")
    parts.append("</svg>")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# SVG -> PNG
# ---------------------------------------------------------------------------

def svg_to_png(svg_string: str) -> bytes:
    """
    Rasterise an SVG string to PNG bytes using cairosvg.

    cairosvg is safe by default (``unsafe=False``): it does not fetch external
    URLs or read local files, so no custom URL fetcher is needed (and cairosvg's
    ``svg2png`` does not accept one). svgbob output is self-contained anyway.
    """
    try:
        import cairosvg  # type: ignore[import]
        return cairosvg.svg2png(bytestring=svg_string.encode(), unsafe=False)
    except Exception as exc:
        raise ConversionError(f"PNG rendering failed: {exc}") from exc
