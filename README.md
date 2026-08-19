# Bilka To Go CLI

Handel ind hos [bilkatogo.dk](https://www.bilkatogo.dk) fra kommandolinjen —
og lad en AI-assistent gøre det for dig via MCP.

Samme idé som [nemlig_cli](https://github.com/josequaresma/nemlig_cli), men
til Bilka To Go.

```
$ bilka search "letmælk" -n 3
3 varer for 'letmælk':

   84120     11,05 kr  Salling - Letmælk 1,5% fedt, 1 l  (11,05 kr/L.)
   19684     12,60 kr  Arla - Letmælk 1,5% fedt, 1 l  (12,60 kr/L.)
   19683     14,05 kr  Arla ØKO - Letmælk 1,5% fedt øko, 1 l  (14,05 kr/L.)

$ bilka shop "letmælk:2" "rugbrød" "kaffe"
[x] letmælk: 2 x Letmælk 1,5% fedt (11,05 kr)
[x] rugbrød: 1 x Solsikkerugbrød (16,00 kr)
[x] kaffe: 1 x Extra formalet kaffe (34,00 kr)
```

## Installation

```bash
git clone https://github.com/augustseptimius-beep/Bilka.git
cd Bilka
./setup.sh
```

`setup.sh` klarer det hele: afhængigheder, login og en projekt-`.mcp.json`
til Claude Code. Vil du kun bruge CLI'en, er `uv sync --extra mcp` nok.

Kræver Python 3.10+ (`fastmcp` findes ikke til 3.9, som macOS stadig leverer).
Har du ikke `uv`, henter `curl -LsSf https://astral.sh/uv/install.sh | sh` den
uden Homebrew eller administratoradgang — og den henter selv en passende
Python. Skal du kun bruge CLI'en og ikke MCP-serveren, er `pip install
requests` nok.

Login sættes i miljøet:

```bash
export BILKA_USERNAME="din@email.dk"
export BILKA_PASSWORD="dit-kodeord"
```

Det er samme login som på hjemmesiden. Sessionen caches i
`~/.config/bilka-cli/session.json` (`chmod 600`), så du ikke logger ind ved
hvert kald. `bilka logout` sletter den.

## Kommandoer

| Kommando | Hvad den gør |
|---|---|
| `bilka search <ord>` | Søg i kataloget (kræver ikke login) |
| `bilka details <id>` | Alle detaljer om en vare |
| `bilka basket` | Vis kurven med total |
| `bilka add <id> [antal]` | Læg i kurven |
| `bilka remove <id> [antal]` | Fjern fra kurven |
| `bilka set <id> <antal>` | Sæt et præcist antal |
| `bilka shop <vare[:antal]>...` | Søg og læg en hel indkøbsliste i kurven |
| `bilka empty --yes` | Tøm kurven |
| `bilka history` | Ordrehistorik |
| `bilka reorder <ordre-id>` | Kopier en tidligere ordre ind i kurven |
| `bilka favorites` | Dine favoritvarer |
| `bilka delivery` | Ledige leveringstider |
| `bilka profile` | Kontooplysninger |
| `bilka checkout [--yes]` | Bestil kurven |

Nyttige flag:

- `--json` på alle kommandoer — virker både før og efter underkommandoen
- `--sort price` — billigst først
- `--sort unit_price` — billigst pr. kilo/liter
- `--offers` — kun varer på tilbud
- `--in-stock` — kun varer på lager

`just` findes også, hvis du har det: `just search mælk`, `just basket`,
`just plan "mælk:2" "rugbrød"`.

### Om prissortering

Bilkas egne prissorterede Algolia-indekser har smidt selve prisfelterne væk,
så de kan hverken vise eller filtrere på pris. Derfor henter CLI'en fra
hovedindekset og sorterer selv over de mest relevante træffere. Det betyder
"billigst blandt de relevante varer" — ikke "billigste vare i hele kataloget
der tilfældigvis matcher ordet".

`--sort unit_price` sammenligner kun varer med **samme** enhed (den enhed
flest træffere bruger), for 0,64 kr/meter er ikke billigere end 9,95 kr/kg.

## Chat med Claude om indkøb

[`docs/claude-desktop.md`](docs/claude-desktop.md) er den fulde opskrift:
MCP-server plus `.claude/skills/bilka-indkoeb`, som spørger til dine kostkrav
første gang og sørger for, at der ikke bliver bestilt uden dit ja.

Kort fortalt: MCP giver Claude hænderne, skillen giver dømmekraften, og
`./setup.sh` klarer opsætningen. Der er to veje, og begge virker:

| Vej | Hvordan | Passer til |
|---|---|---|
| **Claude Code** | `.mcp.json` i projektmappen, indlæses automatisk | Virker altid, ingen installation |
| **`.mcpb`-extension** | Settings → Extensions → Install Extension | Den almindelige chat i Claude-appen |

`setup.sh` bygger begge dele i samme kørsel.

**Settings → Connectors er derimod ikke en vej** — det felt kræver en
HTTPS-URL og er kun til fjernservere, ikke lokale som denne.

### Dine egne præferencer

Skillen leder efter `mine-praeferencer.md` ved siden af `SKILL.md`. Den følger
**ikke** med i git — den er din, og den bliver liggende når du opdaterer
projektet.

Findes filen ikke, spørger Claude til dine kostkrav første gang du handler.
Du kan også skrive den selv. Den er almindelig tekst, og der er en skabelon i
[`docs/claude-desktop.md`](docs/claude-desktop.md#3-dine-egne-præferencer).

Det er her det bliver rart at bruge: skriver du dine faste varer ind med
mængder, kan du nøjes med at sige *"læg det sædvanlige i kurven"*.

## MCP-server

Så en assistent kan handle for dig:

```bash
uv run --extra mcp server.py
```

I projektets `.mcp.json` (det er den `setup.sh` skriver). Peg på venv'ens
Python med fuld sti — MCP-klienter arver ikke altid din `PATH`, så en bar `uv` eller
`python3` fejler tit med `spawn ENOENT`:

```json
{
  "mcpServers": {
    "bilka": {
      "command": "/sti/til/Bilka/.venv/bin/python",
      "args": ["server.py"],
      "cwd": "/sti/til/Bilka",
      "env": {
        "BILKA_USERNAME": "din@email.dk",
        "BILKA_PASSWORD": "dit-kodeord"
      }
    }
  }
}
```

17 tools: `search_products`, `get_product`, `get_basket`, `add_to_basket`,
`remove_from_basket`, `set_basket_quantity`, `add_shopping_list`,
`empty_basket`, `add_voucher`, `order_history`, `order_details`, `reorder`,
`favorites`, `delivery_dates`, `set_delivery_date`, `profile`, `checkout`.

`add_shopping_list` er den interessante: giv den en liste som
`[{"query": "letmælk", "quantity": 2}]`, så søger den, lægger bedste træffer
i kurven og returnerer både det valgte og alternativerne, så du kan tjekke
efter.

## Bestilling koster penge

Det er indbygget to spærringer, fordi `checkout` bruger det gemte betalingskort
på kontoen:

1. `checkout` kører **dry-run** som standard og viser kun hvad der ville blive
   bestilt. Der skal `--yes` (CLI) eller `confirm=True` (MCP) til.
2. MCP-serveren nægter at bestille overhovedet, med mindre
   `BILKA_ALLOW_CHECKOUT=1` er sat i miljøet.

Lad nummer to være slået fra indtil du har set kurven med dine egne øjne.
Alt andet — søgning, kurv, levering — er harmløst og kan altid rulles tilbage
på hjemmesiden.

## Sikkerhed og hemmeligheder

Hvad der ligger hvor, og hvorfor:

| Hvad | Hvor | Beskyttelse |
|---|---|---|
| Dit kodeord | `.mcp.json` (Claude Code) eller Claudes egen sikre opbevaring (`.mcpb`) | `.mcp.json` er gitignored og skrives med `0600`; `.mcpb`-vejen skriver det aldrig til disk |
| Session (JWT + cookie) | `~/.config/bilka-cli/session.json` | Oprettes med `0600` fra starten, udløber efter en time |
| Algolia- og Gigya-nøgler | Hardkodet i `bilka_cli.py` | Ikke hemmeligheder — de ligger i klartekst i Bilkas egen frontend og er kun søge- og login-nøgler, ikke adgang til din konto |

**`.mcpb`-vejen er den sikreste**, fordi kodeordet indsamles af Claudes egen
installationsdialog og aldrig havner i en fil, dette projekt skriver.

Tre ting værd at vide:

- Der er **ingen adgangskontrol mellem Claude og din konto** ud over det, der
  står i skillen. Serveren kan lægge i kurv og læse dine ordrer, så længe den
  kører. `checkout` er den eneste handling, der koster penge, og den er
  spærret to steder (se nedenfor).
- Klienten **verificerer TLS** og sender kun til `bilkatogo.dk`,
  `accounts.eu1.gigya.com` og Algolia. Intet går andre steder hen.
- Kører du `bilka_cli.py` direkte i en terminal med `export BILKA_PASSWORD=...`,
  havner kodeordet i din shell-historik. `./setup.sh` undgår det ved at læse
  det skjult.

Fandt du et sikkerhedsproblem, så åbn et issue — eller bare en PR.

## Arkitektur

Alt klientlogik ligger i `bilka_cli.py`. `server.py` eksponerer det kun som
MCP-tools. Nye endpoints hører hjemme i `bilka_cli.py`.

Bilka To Go kører på tre uafhængige backends:

| Funktion | Backend |
|---|---|
| Søgning | Algolia (`prod_BILKATOGO_PRODUCTS`, ~36.900 varer) |
| Login | Gigya → JWT → Iposen-session |
| Kurv, ordrer, levering | Iposen (`api.bilkatogo.dk`, PHP) |

Se [`bilka_api.md`](bilka_api.md) for den fulde endpoint-dokumentation,
inklusive de faldgruber der koster tid: priser er i **øre**, `count` på
`ChangeLineCount` er et **absolut** antal (`count=0` fjerner linjen),
`eid > 0` betyder ikke nødvendigvis fejl, og Gigya-login må **ikke** sende
`targetEnv`.

Kurven kommer tilbage i tre lag — kategorigrupper, poster, `orderlines` —
med gebyrer blandet ind mellem varerne under overskriften "Services".

Alt er afprøvet mod en rigtig konto: login, kurv, tilføj/fjern/sæt antal,
indkøbslister, favoritter, leveringstider, ordrehistorik og profil.
`checkout` er som det eneste ikke kørt igennem — det ville koste penge.

Endpointene er reverse engineered fra frontendens JavaScript. Der er intet
officielt API, så det kan holde op med at virke uden varsel.

## Licens og ansvar

[MIT](LICENSE) — brug det til hvad du vil.

Projektet er **ikke tilknyttet Salling Group eller Bilka**. Det taler med et
udokumenteret API, som Bilka kan lukke eller ændre uden varsel, og licensen
dækker koden her — ikke en tilladelse fra Bilka til at bruge deres API. Brug
det til din egen konto og dine egne indkøb, og lad være med at hamre løs på
deres servere.
