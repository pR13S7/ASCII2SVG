from __future__ import annotations

import base64

from flask import (
    Blueprint,
    flash,
    render_template,
    request,
)
from flask.typing import ResponseReturnValue

from .converter import ConversionError, ascii_to_svg, svg_to_png, text_to_svg

bp = Blueprint("main", __name__)

_MAX_TEXT_BYTES = 64 * 1024  # 64 KB (also enforced by MAX_CONTENT_LENGTH)
_VALID_THEMES = {"light", "dark"}
_DEFAULT_THEME = "light"
_VALID_MODES = {"diagram", "text"}
_DEFAULT_MODE = "text"  # most pasted input is Unicode box-drawing / tables


@bp.get("/")
def index() -> str:
    return render_template(
        "index.html", text="", format="svg", theme=_DEFAULT_THEME, mode=_DEFAULT_MODE
    )


@bp.post("/")
@bp.post("/convert")
def convert() -> ResponseReturnValue:
    text: str = request.form.get("text", "")
    output_format: str = request.form.get("format", "svg").lower()
    theme: str = request.form.get("theme", _DEFAULT_THEME).lower()
    mode: str = request.form.get("mode", _DEFAULT_MODE).lower()

    # Whitelist theme / mode — unknown values silently fall back to defaults.
    if theme not in _VALID_THEMES:
        theme = _DEFAULT_THEME
    if mode not in _VALID_MODES:
        mode = _DEFAULT_MODE

    def _form(status: int) -> ResponseReturnValue:
        return render_template(
            "index.html", text=text, format=output_format, theme=theme, mode=mode
        ), status

    # --- guards (re-render so user input is preserved) ---
    if not text.strip():
        flash("Input text cannot be empty.")
        return _form(400)

    if len(text.encode()) > _MAX_TEXT_BYTES:
        flash("Input exceeds 64 KB limit.")
        return _form(400)

    if output_format not in ("svg", "png"):
        flash("Invalid output format — choose SVG or PNG.")
        return _form(400)

    # 'text' mode renders input verbatim in monospace (Unicode box-drawing,
    # tables, prose). 'diagram' mode runs svgbob for hand-drawn ASCII art.
    try:
        if mode == "diagram":
            svg = ascii_to_svg(text, theme=theme)
        else:
            svg = text_to_svg(text, theme=theme)
    except ConversionError as exc:
        flash(str(exc))
        return _form(422)

    if output_format == "png":
        try:
            png_bytes = svg_to_png(svg)
        except ConversionError as exc:
            flash(str(exc))
            return _form(422)
        data_b64 = base64.b64encode(png_bytes).decode("ascii")
        result = {
            "data_uri": f"data:image/png;base64,{data_b64}",
            "filename": "diagram.png",
        }
    else:
        data_b64 = base64.b64encode(svg.encode("utf-8")).decode("ascii")
        result = {
            "data_uri": f"data:image/svg+xml;base64,{data_b64}",
            "filename": "diagram.svg",
        }

    # Render the page with an inline preview + a download link (data URI), so
    # the user reviews the result before downloading. No server-side storage.
    return render_template(
        "index.html",
        text=text,
        format=output_format,
        theme=theme,
        mode=mode,
        result=result,
    )
