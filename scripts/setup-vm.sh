#!/usr/bin/env bash
#
# setup-vm.sh — Reproducible developer-VM bootstrap for Pantry Pirate Radio.
#
# Idempotent: safe to re-run. Targets a fresh Ubuntu 22.04/24.04 host.
# Mirrors what CI (.github/workflows/ci.yml) and the devcontainer expect.
#
# What it does:
#   Phase 1  Docker Engine (moby) + Compose v2 + buildx        [needs sudo]
#   Phase 2  git submodules (public always; private scrapers if a token exists)
#   Phase 3  .env (only warns if missing — never overwrites/creates secrets)
#   Phase 4  Quality gates: PII pre-commit hook + (optional) native Python 3.11/Poetry
#
# It deliberately does NOT bring the stack up or create a .env with secrets.
# After this script:  ./bouy up --with-init   then   ./bouy test --pytest
#
# Flags:
#   --no-native     Skip native Python 3.11 + Poetry (stay strictly Docker-first)
#   --no-docker     Skip Docker install (already present)
#   -h | --help     Show this help
#
# Env:
#   SUBMODULE_TOKEN   GitHub PAT (private-repo scope) for app/scraper/scrapers.
#                     If unset, falls back to `gh auth` credentials; if neither
#                     is available, the private scrapers submodule is skipped.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

INSTALL_NATIVE=1
INSTALL_DOCKER=1
for arg in "$@"; do
  case "$arg" in
    --no-native) INSTALL_NATIVE=0 ;;
    --no-docker) INSTALL_DOCKER=0 ;;
    -h|--help) sed -n '2,40p' "$0"; exit 0 ;;
    *) echo "Unknown flag: $arg" >&2; exit 2 ;;
  esac
done

log()  { printf '\033[0;34m>>> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m!!! %s\033[0m\n' "$*"; }
ok()   { printf '\033[0;32m✓   %s\033[0m\n' "$*"; }

# ---------------------------------------------------------------------------
# Phase 1 — Docker Engine + Compose v2 + buildx (moby, NOT Docker Desktop)
# bouy hardcodes `docker compose` (v2 plugin) and base.yml needs Compose >= 2.24.
# ---------------------------------------------------------------------------
if [ "$INSTALL_DOCKER" = 1 ]; then
  if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    ok "Docker + Compose v2 already present ($(docker --version))"
  else
    log "Phase 1: installing Docker Engine + Compose v2 + buildx"
    sudo install -m 0755 -d /etc/apt/keyrings
    if [ ! -f /etc/apt/keyrings/docker.asc ]; then
      sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
      sudo chmod a+r /etc/apt/keyrings/docker.asc
    fi
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
      | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
    sudo apt-get update -qq
    sudo apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    sudo systemctl enable --now docker
    ok "Docker installed: $(docker --version)"
  fi
  # Ensure the invoking user can reach the daemon without sudo.
  if ! id -nG "$USER" | tr ' ' '\n' | grep -qx docker; then
    log "Adding $USER to the 'docker' group"
    sudo usermod -aG docker "$USER"
    warn "You must start a NEW shell (or run 'newgrp docker') for group membership to take effect."
    warn "Until then, prefix bouy with: sg docker -c './bouy ...'"
  else
    ok "$USER is in the 'docker' group"
  fi
fi

# ---------------------------------------------------------------------------
# Phase 2 — git submodules
# Public ones unconditionally; private scrapers only if a token/creds exist.
# ---------------------------------------------------------------------------
log "Phase 2: initializing public submodules (HSDS, GeoJSON)"
git submodule update --init docs/HSDS docs/GeoJson/States
ok "Public submodules ready"

if [ -d app/scraper/scrapers/.git ] || [ -f app/scraper/scrapers/.git ]; then
  ok "Private scrapers submodule already initialized"
elif [ -n "${SUBMODULE_TOKEN:-}" ]; then
  log "Phase 2: initializing private scrapers submodule (SUBMODULE_TOKEN)"
  git config --global url."https://${SUBMODULE_TOKEN}@github.com/".insteadOf "https://github.com/"
  git submodule update --init app/scraper/scrapers
  ok "Private scrapers submodule ready"
elif command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
  log "Phase 2: initializing private scrapers submodule (gh credentials)"
  gh auth setup-git
  if git submodule update --init app/scraper/scrapers; then
    ok "Private scrapers submodule ready"
  else
    warn "Could not clone private scrapers (gh token lacks access?). Continuing with public framework only."
  fi
else
  warn "No SUBMODULE_TOKEN and no gh auth — skipping private scrapers. System runs on the public framework only."
fi

chmod +x ./bouy

# ---------------------------------------------------------------------------
# Phase 3 — .env (NEVER created with secrets by this script)
# ---------------------------------------------------------------------------
if [ -f .env ]; then
  ok ".env present"
else
  warn ".env is MISSING. Create it before 'bouy up':"
  warn "    ./bouy setup            # interactive wizard"
  warn "  or copy .env.example to .env and fill in a real LLM key."
fi
[ -f .env.test ] && ok ".env.test present (committed; used by ./bouy test)" || warn ".env.test missing — tests need it"

# ---------------------------------------------------------------------------
# Phase 4 — Quality gates
# ---------------------------------------------------------------------------
log "Phase 4: wiring PII/secret pre-commit scanner"
chmod +x .githooks/pre-commit
git config core.hooksPath .githooks
ok "core.hooksPath = .githooks (fast secret/PII scan; bypass with --no-verify)"

if [ "$INSTALL_NATIVE" = 1 ]; then
  if ! command -v python3.11 >/dev/null 2>&1; then
    log "Phase 4: installing Python 3.11 (deadsnakes) for CI-parity static gates"
    sudo add-apt-repository -y ppa:deadsnakes/ppa
    sudo apt-get update -qq
    sudo apt-get install -y -qq python3.11 python3.11-venv python3.11-dev build-essential libpq-dev
  fi
  export PATH="$HOME/.local/bin:$PATH"
  if ! command -v poetry >/dev/null 2>&1; then
    log "Phase 4: installing Poetry"
    curl -sSL https://install.python-poetry.org | python3 -
  fi
  log "Phase 4: poetry install (in-project venv on Python 3.11)"
  poetry config virtualenvs.in-project true
  poetry env use python3.11
  poetry install --no-interaction --no-ansi
  ok "Native tooling ready: $(poetry run black --version 2>/dev/null | head -1)"
  warn "Add Poetry to PATH permanently: echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.bashrc"
else
  log "Phase 4: skipping native Python/Poetry (--no-native). Use './bouy test' for all gates."
fi

# ---------------------------------------------------------------------------
log "Setup complete. Next steps:"
echo "    ./bouy up --with-init        # boot stack + seed DB (first run is slow)"
echo "    ./bouy ps                    # confirm services healthy"
echo "    ./bouy test --pytest         # verify the dockerized test path"
echo
echo "  API:          http://localhost:8000/docs"
echo "  RQ dashboard: http://localhost:9181"
[ "$INSTALL_NATIVE" = 1 ] && echo "  Fast local gates: poetry run black/ruff/mypy app tests"
