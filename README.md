# ASCII2SVG

A minimal Flask web application that converts ASCII art into SVG or PNG files.

## Features

- Paste ASCII art in the browser and download it as **SVG** or **PNG**
- **Light / Dark diagram theme** — choose diagram colours (dark theme PNGs get a solid `#1e1e1e` background so light strokes remain visible)
- 64 KB input limit enforced both client-side and server-side
- SSRF-safe PNG rendering via cairosvg
- Non-root Docker container with read-only filesystem
- Auto-deploy git hook (`hooks/post-merge`)

## Quick start

### 1. (Optional) Set a persistent SECRET_KEY

`SECRET_KEY` is now optional.  If you leave it blank, the container
entrypoint auto-generates an ephemeral key on each start.  The only
consequence of an ephemeral key is that in-flight flash messages reset on
container restart — acceptable for most deployments.

To keep flash messages stable across restarts, set the key explicitly:

```bash
cp .env.example .env
# Edit .env and set SECRET_KEY to a stable value:
#   python -c "import secrets; print(secrets.token_hex(32))"
```

### 2. Run with Docker Compose

```bash
docker compose up --build
```

Open [http://localhost:8003](http://localhost:8003).

### 3. Run locally (dev)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# SECRET_KEY is required when running outside Docker (entrypoint.sh not used):
SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))") \
  flask --app wsgi:application run --debug
```

## Project layout

```
ASCII2SVG/
├── app/
│   ├── __init__.py        # create_app() factory
│   ├── converter.py       # ascii_to_svg, svg_to_png, SSRF guard
│   ├── routes.py          # Flask Blueprint (GET /, POST /convert)
│   ├── templates/
│   │   └── index.html
│   └── static/
│       └── style.css
├── hooks/
│   └── post-merge         # Auto-deploy hook (git config core.hooksPath hooks)
├── wsgi.py                # Gunicorn entry point
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

## Auto-deploy hook

To enable auto-deployment on `git pull`:

```bash
git config core.hooksPath hooks
```

This tells Git to use the `hooks/` directory directly, so `hooks/post-merge`
runs after every merge without copying files.

The hook rebuilds and restarts containers automatically after every merge
(`docker compose up -d --build`).

**Notes:**
- **First deploy must be run manually** — `post-merge` does not fire on the
  initial clone.  Run `docker compose up -d --build` once by hand.
- **The deploy user must be in the `docker` group** (or use rootless Docker),
  otherwise the hook will fail with a permission error:
  `sudo usermod -aG docker $USER && newgrp docker`

## Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `SECRET_KEY` | No | Flask session secret. Auto-generated ephemerally if blank (flash messages reset on restart). Set explicitly for stability. |
| `SVGBOB_BIN` | No | Path/name of the svgbob binary. Defaults to `svgbob`. |

## Build gates

**B1 — svgbob binary name and flag names:** `cargo install svgbob_cli` typically produces a binary named `svgbob`. Confirm via the `ls -la /usr/local/cargo/bin/` output printed during `docker build`. Also verify flag names via `svgbob --help` — the flags `--background`, `--fill-color`, and `--font-family` are documented-likely but differ across versions. Adjust in `app/converter.py` if needed.

**B2 — font package:** `fonts-dejavu-core` and `fontconfig` are installed in the Docker runtime stage. Without these, cairosvg renders `<text>` elements as blank glyphs in PNG output. The build smoke-test asserts the PNG is non-trivial to catch this regression.

## Security notes

- The `url_fetcher` in `converter.py` refuses all remote resource fetching:
  this app converts ASCII text to SVG; no external URLs are ever embedded in
  the generated output, so remote fetching is unnecessary.  `data:` URIs
  (handled internally by cairosvg) are unaffected.
- **No CSRF tokens** — the `/convert` endpoint is a stateless, unauthenticated
  transform that returns a file download.  There is no server-side session
  state to mutate and no authenticated action an attacker could trigger via a
  cross-site request, so CSRF tokens are intentionally omitted.
- The Docker container runs as a non-root user with a read-only root filesystem.
- `.env` is excluded from both `.gitignore` and `.dockerignore`.
