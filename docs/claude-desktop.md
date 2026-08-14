# Opsætning i Claude Desktop

To dele, der løser hver sin halvdel:

- **MCP-serveren** giver Claude hænderne — søge, lægge i kurv, se totalen.
- **Skillen** giver dømmekraften — kostkrav, rutine, og at der ikke bestilles
  uden dit ja.

Sæt MCP op først. Skillen er ikke til megen nytte uden den.

---

## 1. MCP-serveren

### Hent koden og installér

```bash
git clone https://github.com/augustseptimius-beep/Bilka.git
cd Bilka
uv sync --extra mcp
```

Har du ikke `uv`, virker `pip install requests fastmcp` også — så skal
kommandoen i config'en bare være `python3` i stedet (se nedenfor).

Notér den fulde sti til mappen, den skal bruges lige om lidt:

```bash
pwd     # fx /Users/august/kode/Bilka
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
      "command": "uv",
      "args": ["run", "--extra", "mcp", "server.py"],
      "cwd": "/HELE/STIEN/TIL/Bilka",
      "env": {
        "BILKA_USERNAME": "din@email.dk",
        "BILKA_PASSWORD": "dit-kodeord"
      }
    }
  }
}
```

Bruger du pip i stedet for uv:

```json
      "command": "python3",
      "args": ["server.py"],
```

Tre ting der typisk går galt:

- **`cwd` skal være den fulde sti.** Ingen `~` og ingen relativ sti.
- **`command` skal kunne findes.** Claude Desktop arver ikke altid din
  `PATH`. Virker det ikke, så skriv den fulde sti — `which uv` (macOS) eller
  `where uv` (Windows) giver den.
- **JSON tåler ikke kommentarer** og heller ikke et komma efter sidste felt.

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
| Ingen bilka-værktøjer i chatten | Config'en er ikke læst — tjek JSON-syntaks og genstart helt |
| `spawn uv ENOENT` | `command` kan ikke findes; skriv fuld sti |
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
