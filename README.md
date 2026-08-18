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

`setup.sh` klarer det hele: afhængigheder, login og
`claude_desktop_config.json`. Vil du kun bruge CLI'en, er `uv sync --extra mcp`
nok.

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

## Claude Desktop

Vil du bare chatte med Claude om indkøb, er
[`docs/claude-desktop.md`](docs/claude-desktop.md) den fulde opskrift: MCP-server
plus `skills/bilka-indkoeb`, som håndhæver kostkrav og sørger for, at der ikke
bliver bestilt uden dit ja.

Kort fortalt: MCP giver Claude hænderne, skillen giver dømmekraften.

## MCP-server

Så en assistent kan handle for dig:

```bash
uv run --extra mcp server.py
```

I `~/.claude.json` eller projektets `.mcp.json`. Peg på venv'ens Python med
fuld sti — MCP-klienter arver ikke altid din `PATH`, så en bar `uv` eller
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
officielt API, så det kan holde op med at virke uden varsel. Projektet er
ikke tilknyttet Salling Group.
