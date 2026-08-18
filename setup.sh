#!/usr/bin/env bash
# Opsætning af Bilka To Go til Claude Desktop.
# Installerer afhængigheder, tester login og skriver config'en.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO"

say()  { printf '\n\033[1m%s\033[0m\n' "$*"; }
ok()   { printf '  \033[32mok\033[0m  %s\n' "$*"; }
warn() { printf '  \033[33m!\033[0m   %s\n' "$*"; }
die()  { printf '\n\033[31mFejl:\033[0m %s\n\n' "$*" >&2; exit 1; }

# --- 1. uv -----------------------------------------------------------------
say "1/5  Afhængigheder"

if ! command -v uv >/dev/null 2>&1; then
    export PATH="$HOME/.local/bin:$PATH"
fi
if ! command -v uv >/dev/null 2>&1; then
    warn "uv mangler - henter den (kræver ikke administratoradgang)"
    curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null 2>&1 \
        || die "kunne ikke hente uv. Installér Python 3.10+ manuelt og prøv igen."
    export PATH="$HOME/.local/bin:$PATH"
fi
command -v uv >/dev/null 2>&1 || die "uv blev installeret, men kan ikke findes. Åbn en ny terminal og kør scriptet igen."
ok "uv $(uv --version 2>/dev/null | awk '{print $2}')"

[ -f pyproject.toml ] || die "pyproject.toml mangler. Er du på den rigtige branch? Prøv: git checkout claude/bilka-to-go-cli-ivem7s"

uv sync --extra mcp >/dev/null 2>&1 || die "uv sync fejlede. Kør 'uv sync --extra mcp' for at se hvorfor."
PY="$REPO/.venv/bin/python"
[ -x "$PY" ] || die "fandt ingen Python i .venv"
ok "Python $("$PY" -c 'import sys; print(".".join(map(str, sys.version_info[:3])))') i .venv"

# --- 2. Røgtest uden login -------------------------------------------------
say "2/5  Forbindelse til Bilka"
"$PY" bilka_cli.py search "letmælk" -n 1 >/dev/null 2>&1 \
    || die "kunne ikke søge. Tjek din netforbindelse."
ok "søgning virker (uden login)"

# --- 3. Login --------------------------------------------------------------
say "3/5  Login"
echo "  Samme login som på bilkatogo.dk. Kodeordet vises ikke mens du taster,"
echo "  og gemmes kun i Claude Desktops config-fil på denne maskine."
echo
printf '  E-mail:   '
read -r BILKA_USER
printf '  Kodeord:  '
read -rs BILKA_PASS
echo

[ -n "$BILKA_USER" ] && [ -n "$BILKA_PASS" ] || die "både e-mail og kodeord skal udfyldes."

BILKA_USERNAME="$BILKA_USER" BILKA_PASSWORD="$BILKA_PASS" \
    "$PY" bilka_cli.py login >/dev/null 2>&1 \
    || die "login blev afvist. Tjek e-mail og kodeord og kør scriptet igen."
ok "logget ind som $BILKA_USER"

# --- 4. Config -------------------------------------------------------------
say "4/5  Claude Desktop"

case "$(uname -s)" in
    Darwin) CFG="$HOME/Library/Application Support/Claude/claude_desktop_config.json" ;;
    *)      CFG="$HOME/.config/Claude/claude_desktop_config.json" ;;
esac
mkdir -p "$(dirname "$CFG")"

if [ -f "$CFG" ]; then
    cp "$CFG" "$CFG.backup-$(date +%Y%m%d-%H%M%S)"
    ok "sikkerhedskopi af eksisterende config gemt"
fi

BILKA_USERNAME="$BILKA_USER" BILKA_PASSWORD="$BILKA_PASS" \
CFG_PATH="$CFG" PY_PATH="$PY" REPO_PATH="$REPO" "$PY" - <<'PYEOF'
import json, os, pathlib

cfg = pathlib.Path(os.environ["CFG_PATH"])
data = {}
if cfg.exists() and cfg.stat().st_size:
    try:
        data = json.loads(cfg.read_text())
    except json.JSONDecodeError:
        raise SystemExit("config-filen indeholder ugyldig JSON - ret eller slet den først")

# Behold andre MCP-servere som de er.
servers = data.setdefault("mcpServers", {})
servers["bilka"] = {
    "command": os.environ["PY_PATH"],
    "args": ["server.py"],
    "cwd": os.environ["REPO_PATH"],
    "env": {
        "BILKA_USERNAME": os.environ["BILKA_USERNAME"],
        "BILKA_PASSWORD": os.environ["BILKA_PASSWORD"],
    },
}
cfg.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
cfg.chmod(0o600)

others = [k for k in servers if k != "bilka"]
print(f"  ok  config skrevet ({len(servers)} server{'e' if len(servers) != 1 else ''}"
      + (f", urørt: {', '.join(others)}" if others else "") + ")")
PYEOF

# --- 5. Skill --------------------------------------------------------------
say "5/5  Indkøbs-skill"
if command -v zip >/dev/null 2>&1 && [ -d skills/bilka-indkoeb ]; then
    (cd skills && rm -f bilka-indkoeb.zip && zip -qr bilka-indkoeb.zip bilka-indkoeb)
    ok "skills/bilka-indkoeb.zip er klar til upload"
else
    warn "kunne ikke pakke skillen - den er valgfri"
fi

cat <<EOF

────────────────────────────────────────────────────────────
Færdig. To ting mangler, som kun du kan gøre:

  1. Genstart Claude Desktop helt (Cmd+Q, ikke bare luk vinduet)

  2. Slå skillen til:
     Settings → Capabilities → slå Code execution og File creation til,
     og upload derefter under Skills:
     $REPO/skills/bilka-indkoeb.zip

Prøv så i Claude Desktop:  "Hvad ligger der i min Bilka-kurv?"

Bestilling er slået fra. Claude kan alt undtagen bruge dit betalingskort.
────────────────────────────────────────────────────────────

EOF
