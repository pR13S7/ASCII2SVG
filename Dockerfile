# ── Stage 1: Build svgbob from crates.io ─────────────────────────────────────
FROM rust:1-slim-bookworm AS builder

RUN cargo install svgbob_cli --locked --version 0.7.6

# B1 — discovery: confirm the real binary name from this output.
# `cargo install svgbob_cli` produces `svgbob_cli` for current versions.
# We rename it to `svgbob` in runtime for a stable app command name.
RUN ls -la /usr/local/cargo/bin/


# ── Stage 2: Python runtime ───────────────────────────────────────────────────
FROM python:3.12-slim-bookworm AS runtime

# System libs required by cairosvg / cairo.
# B2 — fonts-dejavu-core + fontconfig are REQUIRED: without a font package,
# cairosvg renders SVG <text> elements as blank glyphs in the PNG output.
# fonts-dejavu-core also provides 'DejaVu Sans Mono', the monospace font used
# for diagram text (preserves ASCII column alignment).
RUN apt-get update && apt-get install -y --no-install-recommends \
      libcairo2 \
      libpango-1.0-0 \
      libpangocairo-1.0-0 \
      libgdk-pixbuf-2.0-0 \
      libffi8 \
      shared-mime-info \
      fontconfig \
      fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# Pre-build the system font cache as root so it is readable on a read-only
# rootfs when the container runs as the unprivileged appuser.
RUN fc-cache -fv

# Copy and normalize binary name from builder stage.
COPY --from=builder /usr/local/cargo/bin/svgbob_cli /usr/local/bin/svgbob

# S1 — link check: fails loud at build time if a required shared lib is absent.
RUN ldd /usr/local/bin/svgbob

# Smoke-test: confirm svgbob is runnable.
RUN svgbob --version

WORKDIR /app

# Install Python deps first (layer-cache friendly)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Smoke-test cairosvg: render an SVG containing a <text> element and assert
# the PNG is non-trivial (> 500 bytes).  Catches missing-font regressions (B2).
RUN python - <<'EOF'
import cairosvg, sys
SVG = (
    b'<svg xmlns="http://www.w3.org/2000/svg" width="200" height="60">'
    b'<rect width="100%" height="100%" fill="#ffffff"/>'
    b'<text x="10" y="40" font-size="20" fill="#000000">Hello</text>'
    b'</svg>'
)
png = cairosvg.svg2png(bytestring=SVG)
assert len(png) > 500, f"PNG too small ({len(png)} bytes) — font rendering may be broken"
print(f"cairosvg smoke-test OK: {len(png)} bytes")
EOF

# Copy application source
COPY app/ app/
COPY wsgi.py .
COPY entrypoint.sh .

# Non-root user
RUN useradd --no-create-home --shell /bin/false appuser \
    && chown appuser:appuser entrypoint.sh \
    && chmod +x entrypoint.sh
USER appuser

EXPOSE 8003

ENTRYPOINT ["./entrypoint.sh"]
CMD ["gunicorn", "--bind", "0.0.0.0:8003", "--workers", "2", "--timeout", "30", "wsgi:application"]
