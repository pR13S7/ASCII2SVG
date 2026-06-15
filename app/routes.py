from __future__ import annotations

import base64

from flask import (
    Blueprint,
    flash,
    render_template,
    request,
)
from flask.typing import ResponseReturnValue

from .converter import ConversionError, ascii_to_svg, svg_to_png

bp = Blueprint("main", __name__)

_MAX_TEXT_BYTES = 64 * 1024  # 64 KB (also enforced by MAX_CONTENT_LENGTH)
_VALID_THEMES = {"light", "dark"}
_DEFAULT_THEME = "light"


@bp.get("/")
def index() -> str:
    return render_template("index.html", text="", format="svg", theme=_DEFAULT_THEME)


@bp.post("/convert")
def convert() -> ResponseReturnValue:
    text: str = request.form.get("text", "")
    output_format: str = request.form.get("format", "svg").lower()
    theme: str = request.form.get("theme", _DEFAULT_THEME).lower()

    # Whitelist theme — unknown values silently fall back to default.
    if theme not in _VALID_THEMES:
        theme = _DEFAULT_THEME

    # --- guards (render_template so user input is preserved) ---
    if not text.strip():
        flash("Input text cannot be empty.")
        return render_template(  # type: ignore[return-value]
            "index.html", text=text, format=output_format, theme=theme
        ), 400

    if len(text.encode()) > _MAX_TEXT_BYTES:
        flash("Input exceeds 64 KB limit.")
        return render_template(  # type: ignore[return-value]
            "index.html", text=text, format=output_format, theme=theme
        ), 400

    if output_format not in ("svg", "png"):
        flash("Invalid output format — choose SVG or PNG.")
        return render_template(  # type: ignore[return-value]
            "index.html", text=text, format=output_format, theme=theme
        ), 400

    try:
        svg = ascii_to_svg(text, theme=theme)
    except ConversionError as exc:
        flash(str(exc))
        return render_template(  # type: ignore[return-value]
            "index.html", text=text, format=output_format, theme=theme
        ), 422

    if output_format == "png":
        try:
            png_bytes = svg_to_png(svg)
        except ConversionError as exc:
            flash(str(exc))
            return render_template(
                "index.html", text=text, format=output_format, theme=theme
            ), 422
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
    # the user reviews the diagram before downloading. No server-side storage,
    # no extra round-trip.
    return render_template(
        "index.html",
        text=text,
        format=output_format,
        theme=theme,
        result=result,
    )
