# Opsætning

Der er to veje, og de virker begge. `setup.sh` bygger begge i samme kørsel:

| Vej | Hvordan | Bemærk |
|---|---|---|
| **Claude Code** | `.mcp.json` i projektmappen | Indlæses automatisk, ingen installation |
| **`.mcpb`-extension** | Settings → Extensions → Install Extension… | Virker i den almindelige chat |

**Settings → Connectors er ikke en mulighed.** Det felt kræver en
`Remote MCP server URL` over HTTPS og er kun til servere, der kører på
nettet — ikke en lokal som denne.

## Den hurtige vej

```bash
git clone https://github.com/augustseptimius-beep/Bilka.git
cd Bilka
./setup.sh
```

Scriptet henter afhængigheder (og `uv`, hvis den mangler), beder om dit
Bilka-login, tester at det virker, og skriver en `.mcp.json` i projektmappen.
Har du en anden `.mcp.json` i forvejen, tages en sikkerhedskopi først.

Bagefter: åbn en Claude Code-session i mappen (`claude` i terminalen, eller
vælg mappen i appens Claude Code-fane). Skillen i `.claude/skills/` og
MCP-serveren i `.mcp.json` bliver fundet automatisk.

Første gang du beder om hjælp til indkøb, spørger Claude til dine kostkrav og
tilbyder at gemme dem i din egen `mine-praeferencer.md`. Se
[afsnit 3](#3-dine-egne-præferencer) hvis du hellere vil skrive den selv.

Resten af dette dokument er den manuelle vej, og hvad du gør hvis noget
driller.

---

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

### Skriv `.mcp.json`

Kopiér skabelonen og udfyld dit login. Filen ligger i projektmappen og er
gitignored, så den aldrig bliver committet:

```bash
cp .mcp.json.example .mcp.json
```

Redigér den til:

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

To ting der typisk går galt:

- **Brug fulde stier i både `command` og `cwd`.** Ingen `~`, ingen relative
  stier. Peg direkte på venv'ens Python — så er den uafhængig af hvilken
  `PATH` Claude Code starter med.
- **JSON tåler ikke kommentarer** og heller ikke et komma efter sidste felt.

Åbn så en Claude Code-session i mappen (`claude` i terminalen, eller vælg
mappen i appens Claude Code-fane). Første gang bliver du typisk bedt om at
godkende projektets MCP-server — sig ja. Værktøjerne dukker op i den
session.

### Bemærk om kodeordet

Det står i klartekst i `.mcp.json`. Filen ligger på din egen maskine, er
gitignored, og forlader ikke maskinen. Men den bør ikke deles eller
synkroniseres til et delt drev.

Skifter du kodeord hos Bilka, retter du det i `.mcp.json` og starter en ny
Claude Code-session. Serveren logger selv ind igen undervejs, så du skal
ikke gøre andet.

---

## 2. Skillen

Claude Code finder selv `.claude/skills/bilka-indkoeb/SKILL.md`, når du
åbner projektmappen — intet at installere. Den aktiverer sig selv, når
samtalen handler om indkøb, eller du kan bede om den ved navn.

---

## 3. Dine egne præferencer

Skillen kender ikke din husstand. Den leder efter en fil ved siden af
`SKILL.md`:

```
.claude/skills/bilka-indkoeb/mine-praeferencer.md
```

Filen er **gitignored** (`.gitignore` linje 21). Den ryger ikke med når du
pusher, og den bliver liggende når du henter opdateringer til projektet. Dine
kostkrav og vaner er dine egne — de hører ikke hjemme i et offentligt repo.

### Sådan kommer du i gang

Du behøver ikke skrive den selv. Findes filen ikke, spørger Claude til dine
kostkrav første gang du beder om hjælp til indkøb, og tilbyder at gemme
svarene. Det er den nemmeste vej.

Vil du hellere skrive den i hånden, er her en skabelon at klippe i:

```markdown
# Mine indkøbspræferencer

## Husstanden
- 2 voksne og et barn på 3 år.
- Vi handler ca. 2 gange om ugen.

## Kostkrav — hårde krav, verificér altid
- Glutenfri: gælder hele husstanden.
- Nøddeallergi: gælder mit barn. Også spor af nødder.

## Præferencer — må vige for pris og tilgængelighed
- Økologi når merprisen er rimelig.
- Helst dansk kød.

## Faste varer — "det sædvanlige"
| Vare | Pr. md |
|---|---|
| Havregryn øko | 2 |
| Bananer | 8 |
| Kaffe, mørkristet | 1 |
| Toiletpapir 8 rl | 1 |

## Spørg altid før du køber
- Kød ud over det faste.
- Alkohol.
```

### Hvad der gør den nyttig

Tre ting betaler sig at få med:

- **Skeln mellem krav og præferencer.** Et helbredskrav gør varen ubrugelig
  hvis det brydes; en præference må vige for prisen. Skillen behandler de to
  slags forskelligt, så skriv hvilken slags det er.
- **Skriv hvem kravet gælder.** "Kun min ene datter skal have det nøddefri"
  giver bedre indkøb end bare "nøddefri", fordi det så kun er hendes varer og
  fællesvarerne der skal tjekkes — ikke hele kurven.
- **Sæt mængder på de faste varer.** Så kan du nøjes med at sige *"læg det
  sædvanlige i kurven"*, og Claude ved hvor meget der skal til.

Har du dine kvitteringer digitalt — fx eksporteret fra en kvitterings-app —
kan du give dem til Claude og bede om at få listen udledt af dem. Så bliver
mængderne dine faktiske, ikke dine gættede.

---

## 4. Eller: .mcpb-extension til den almindelige chat

Vil du bruge det i den almindelige chat i stedet for Claude Code, bygger
`setup.sh` også `bilka-to-go.mcpb` — en installerbar pakke til netop den
overflade. Den findes under **Settings → Extensions** (ikke Connectors).

Dobbeltklik filen, eller **Settings → Extensions → Advanced settings →
Install Extension…**. Installationsdialogen beder om din Bilka-mail og
kodeord og gemmer dem selv sikkert — vi skriver dem ikke til en fil, i
modsætning til `.mcp.json`.

Bundlen peger på den samme `.venv`-Python som Claude Code bruger (angivet i
`manifest.json`'s `command`-felt), så den undgår macOS' for gamle
system-Python. Det gør den til gengæld knyttet til denne ene maskine og
denne ene sti — kør `./setup.sh` igen, hvis du flytter eller kloner mappen
et andet sted, så pakkes den til den nye sti.

Skillen er ikke inde i `.mcpb`-filen (kun MCP-serveren er). Vil du have den
med i den almindelige chat, skal den uploades separat under
Settings → Capabilities → Skills som en zip:

```bash
cd .claude/skills && zip -r ../../skills.zip bilka-indkoeb
```

---

## 5. Prøv det

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
| Ingen bilka-værktøjer i den almindelige chat | Extensionen er ikke installeret — se afsnit 3. Connectors virker ikke til lokale servere |
| Ingen bilka-værktøjer i Claude Code | `.mcp.json` mangler, har ugyldig JSON, eller du sagde nej til godkendelsesprompten første gang |
| `spawn ... ENOENT` | `command` i `.mcp.json` kan ikke findes; skriv fuld sti til `.venv`-Python |
| `Gigya-login fejlede: Invalid LoginID` | Forkert mail eller kodeord i `env` |
| Søgning virker, men kurven fejler | Login er problemet, ikke serveren |
| Skillen aktiveres ikke | Du sidder ikke i projektmappen, eller `.claude/skills/bilka-indkoeb/SKILL.md` mangler |

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
