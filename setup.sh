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

# --- 4. Projekt-MCP-config til Claude Code -----------------------------
say "4/5  MCP-config"

MCP_JSON="$REPO/.mcp.json"
if [ -f "$MCP_JSON" ]; then
    cp "$MCP_JSON" "$MCP_JSON.backup-$(date +%Y%m%d-%H%M%S)"
    ok "sikkerhedskopi af eksisterende .mcp.json gemt"
fi

BILKA_USERNAME="$BILKA_USER" BILKA_PASSWORD="$BILKA_PASS" \
MCP_PATH="$MCP_JSON" PY_PATH="$PY" REPO_PATH="$REPO" "$PY" - <<'PYEOF'
import json, os, pathlib

cfg = pathlib.Path(os.environ["MCP_PATH"])
data = {}
if cfg.exists() and cfg.stat().st_size:
    try:
        data = json.loads(cfg.read_text())
    except json.JSONDecodeError:
        raise SystemExit(".mcp.json indeholder ugyldig JSON - ret eller slet den først")

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
print("  ok  .mcp.json skrevet i projektmappen")
PYEOF

warn ".mcp.json indeholder dit kodeord i klartekst og er ikke committet (se .gitignore)"

# Nyere udgaver af Claude-appen (den samlede app med Cowork og Claude Code)
# bruger IKKE claude_desktop_config.json til den almindelige chat - det er
# grunden til at MCP-værktøjer kan mangle der, selvom skillen indlæses fint.
# .mcp.json er den mekanisme Claude Code selv bruger til projekt-scopede
# MCP-servere, og virker derfor uafhængigt af hvilken variant af appen du har.
case "$(uname -s)" in
    Darwin) OLD_CFG="$HOME/Library/Application Support/Claude/claude_desktop_config.json" ;;
    *)      OLD_CFG="$HOME/.config/Claude/claude_desktop_config.json" ;;
esac
if [ -f "$OLD_CFG" ] && grep -q '"mcpServers"' "$OLD_CFG" 2>/dev/null; then
    ok "fandt også mcpServers i $OLD_CFG - den er ikke rørt, ryd evt. op i den manuelt"
fi

# --- 5. Skill ---------------------------------------------------------
say "5/6  Indkøbs-skill"
if [ -d .claude/skills/bilka-indkoeb ]; then
    ok ".claude/skills/bilka-indkoeb findes - Claude Code indlæser den automatisk i denne mappe"
else
    warn ".claude/skills/bilka-indkoeb mangler - den er valgfri, men bør ligge i repoet"
fi

# --- 6. .mcpb - installerbar extension til den almindelige Claude-chat -----
say "6/6  Extension til Claude-chatten (.mcpb)"
if [ -f mcpb/manifest.template.json ] && command -v zip >/dev/null 2>&1; then
    BUILD="$(mktemp -d)"
    PY_PATH="$PY" "$PY" - "$BUILD" <<'PYEOF'
import json, sys, pathlib
build = pathlib.Path(sys.argv[1])
tpl = pathlib.Path("mcpb/manifest.template.json").read_text()
tpl = tpl.replace("{{PYTHON}}", __import__("os").environ["PY_PATH"])
json.loads(tpl)  # fejl tidligt hvis substitutionen ødelagde JSON'en
(build / "manifest.json").write_text(tpl)
PYEOF
    cp server.py bilka_cli.py "$BUILD/"
    rm -f bilka-to-go.mcpb
    (cd "$BUILD" && zip -qr "$REPO/bilka-to-go.mcpb" manifest.json server.py bilka_cli.py)
    rm -rf "$BUILD"
    ok "bilka-to-go.mcpb pakket - peger på $PY"
else
    warn "kunne ikke pakke .mcpb (mangler zip eller mcpb/manifest.template.json) - spring over"
fi

cat <<EOF

────────────────────────────────────────────────────────────
Færdig. To måder at bruge det på:

  A) Claude Code (virker altid, ingen ekstra trin):
     Åbn en Claude Code-session i denne mappe ($REPO) - i terminalen: "claude".
     Den finder selv .mcp.json og .claude/skills/bilka-indkoeb, og beder om
     lov til MCP-serveren første gang.

  B) Almindelig Claude-chat, hvis din app har Settings → Extensions:
     Dobbeltklik $REPO/bilka-to-go.mcpb (eller Settings → Extensions →
     Advanced settings → Install Extension…). Du bliver bedt om din
     Bilka-mail og kodeord i selve installationsdialogen - vi skriver dem
     ikke til en fil. Skillen skal uploades separat samme sted som en zip:
     skal du bruge den, kør: (cd .claude/skills && zip -r ../../skills.zip bilka-indkoeb)

Prøv så:  "Hvad ligger der i min Bilka-kurv?"

Settings → Connectors kræver en HTTPS-URL og er kun til fjernservere -
det er ikke en vej til denne lokale server.

Bestilling er slået fra. Claude kan alt undtagen bruge dit betalingskort.
────────────────────────────────────────────────────────────

EOF
