# Opsætning i Claude Desktop

To dele, der løser hver sin halvdel:

- **MCP-serveren** giver Claude hænderne — søge, lægge i kurv, se totalen.
- **Skillen** giver dømmekraften — kostkrav, rutine, og at der ikke bestilles
  uden dit ja.

Sæt MCP op først. Skillen er ikke til megen nytte uden den.

---

## 1. MCP-serveren

### Hent koden og installér

**Tjek din Python-version først.** MCP-serveren bruger `fastmcp`, som kræver
Python 3.10 eller nyere:

```bash
python3 --version
```

macOS leverer stadig Python 3.9 med Xcode Command Line Tools. Får du `3.9.x`,
fejler installationen med `Could not find a version that satisfies the
requirement fastmcp` — pakken findes simpelthen ikke til 3.9.

### Med uv (nemmest — henter selv en passende Python)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source "$HOME/.local/bin/env"          # eller åbn en ny terminal

git clone https://github.com/augustseptimius-beep/Bilka.git
cd Bilka
uv sync --extra mcp
.venv/bin/python -c "import fastmcp, requests; print('afhængigheder OK')"
```

`uv` kræver hverken Homebrew eller administratoradgang og henter selv den
Python der skal bruges. Den laver en `.venv` i projektmappen, som config'en
peger direkte ind i.

### Uden uv

Har du allerede Python 3.10+ (fx via Homebrew: `brew install python@3.12`):

```bash
git clone https://github.com/augustseptimius-beep/Bilka.git
cd Bilka
python3.12 -m venv .venv                # brug din 3.10+ binær
.venv/bin/pip install --quiet --upgrade pip requests fastmcp
.venv/bin/python -c "import fastmcp, requests; print('afhængigheder OK')"
```

Uanset vejen: brug en venv frem for en global installation. Den giver en fast,
absolut sti til Python — netop hvad Claude Desktop skal bruge, fordi den ikke
arver din `PATH`. Nyere systemer afviser desuden ofte `pip install` uden for
en venv (`externally-managed-environment`).

Notér den fulde sti til mappen, den skal bruges lige om lidt:

```bash
pwd     # fx /Users/august/Bilka
```

### Redigér config-filen

| System | Sti |
|---|---|
| macOS | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Windows | `%APPDATA%\Claude\claude_desktop_config.json` |

Findes filen ikke, så opret den. Indhold:

```json
{
  "mcpServers": {
    "bilka": {
      "command": "/HELE/STIEN/TIL/Bilka/.venv/bin/python",
      "args": ["server.py"],
      "cwd": "/HELE/STIEN/TIL/Bilka",
      "env": {
        "BILKA_USERNAME": "din@email.dk",
        "BILKA_PASSWORD": "dit-kodeord"
      }
    }
  }
}
```

På Windows hedder Python i venv'en `.venv\Scripts\python.exe`, og stier
skal skrives med dobbelte backslashes: `C:\\Users\\dig\\Bilka`.

Tre ting der typisk går galt:

- **Brug fulde stier i både `command` og `cwd`.** Ingen `~`, ingen relative
  stier. Claude Desktop arver ikke din `PATH`, så en bar `python3` eller
  `uv` fejler tit med `spawn ENOENT`, selvom den virker i terminalen. Peger
  du direkte på venv'ens Python, findes den altid.
- **JSON tåler ikke kommentarer** og heller ikke et komma efter sidste felt.
- **Genstart programmet helt**, ikke bare vinduet.

Genstart Claude Desktop helt (luk vinduet er ikke nok — afslut programmet).
Værktøjerne dukker op under værktøjsikonet i chatten.

### Bemærk om kodeordet

Det står i klartekst i config-filen. Filen ligger på din egen maskine og
forlader den ikke, og det er samme model som alle andre lokale MCP-servere.
Men det er værd at vide, og filen bør ikke deles eller synkroniseres til et
delt drev.

Skifter du kodeord hos Bilka, skal det rettes her og Claude Desktop
genstartes. Serveren logger selv ind igen undervejs, så du skal ikke gøre
andet.

---

## 2. Skillen

Skills kræver, at **Code execution** og **File creation** er slået til under
Settings → Capabilities. Ellers indlæses de ikke.

Pak skillen som zip — mappen skal med, ikke kun filen:

```bash
cd Bilka/skills
zip -r bilka-indkoeb.zip bilka-indkoeb
```

Så: **Settings → Capabilities → Skills → Add**, vælg `bilka-indkoeb.zip`,
og slå den til.

Claude aktiverer den selv, når samtalen handler om indkøb. Du kan også bare
sige "brug bilka-indkoeb".

---

## 3. Prøv det

```
Hvad ligger der i min Bilka-kurv?
```

```
Læg havregryn, mælk og bananer i kurven — glutenfri og øko hvor det kan lade sig gøre
```

```
Hvad koster økologiske bananer, og hvad er billigst pr. kilo?
```

Claude bestiller ikke af sig selv. Skal der bestilles, skal du sige det
udtrykkeligt, og du bliver bedt om at bekræfte totalen først.

---

## Hvis noget driller

| Symptom | Årsag |
|---|---|
| `No matching distribution found for fastmcp` | Python 3.9 — fastmcp kræver 3.10+ |
| Ingen bilka-værktøjer i chatten | Config'en er ikke læst — tjek JSON-syntaks og genstart helt |
| `spawn ... ENOENT` | `command` kan ikke findes; skriv fuld sti til `.venv`-Python |
| `Gigya-login fejlede: Invalid LoginID` | Forkert mail eller kodeord i `env` |
| Søgning virker, men kurven fejler | Login er problemet, ikke serveren |
| Skillen aktiveres ikke | Code execution og File creation slået fra |

Serveren skriver fejl til Claude Desktops logfil:

- macOS: `~/Library/Logs/Claude/mcp-server-bilka.log`
- Windows: `%APPDATA%\Claude\logs\mcp-server-bilka.log`

Vil du fejlsøge uden om Claude, så kør CLI'en direkte — samme kode, samme fejl:

```bash
export BILKA_USERNAME="din@email.dk" BILKA_PASSWORD="..."
python3 bilka_cli.py basket
```

---

## Bestilling er slået fra

`checkout` er spærret to steder. Skillen beder om dit ja, og serveren nægter
uanset hvad, med mindre `BILKA_ALLOW_CHECKOUT=1` står i `env`.

Lad den være væk, indtil du har set nogle kurve blive samlet rigtigt. Uden
den kan Claude gøre alt undtagen at bruge dit betalingskort — og alt andet
kan rulles tilbage på hjemmesiden.
