#!/usr/bin/env sh
set -e

# Auto-generate SECRET_KEY if not supplied.
# The key is ephemeral (regenerated each container start), which only affects
# in-flight flash messages across restarts — acceptable for stateless use.
# Set SECRET_KEY explicitly in .env (or docker-compose.yml) to persist it.
if [ -z "$SECRET_KEY" ]; then
    export SECRET_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')"
    echo "[entrypoint] SECRET_KEY not set — generated ephemeral key" >&2
fi

exec "$@"
