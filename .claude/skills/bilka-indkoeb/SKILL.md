---
name: bilka-indkoeb
description: Handel ind hos Bilka To Go via bilka-MCP-serveren. Brug den når brugeren vil købe dagligvarer, sætte varer i kurven, planlægge mad og handle ind til det, spørger hvad noget koster hos Bilka, vil bestille "det samme som sidst", eller beder om at få tjekket eller ryddet op i kurven. Skeln mellem hårde kostkrav og præferencer, og bekræft altid før bestilling.
---

# Indkøb hos Bilka To Go

Værktøjerne kommer fra `bilka`-MCP-serveren (`search_products`, `add_to_basket`,
`get_basket`, `add_shopping_list`, `reorder`, `checkout` m.fl.).

> **Tilpas dette afsnit til din egen husstand.** Kostkrav og faste varer
> herunder er eksempler, der viser mønstret — ikke noget der passer til
> alle. Erstat dem med dine egne, før du bruger skillen i praksis.

## Kostkrav — det vigtigste

Skeln mellem helbredskrav og smagssager. Bliver et helbredskrav brudt, er
varen ubrugelig, ikke bare ikke-optimal — så eksemplet herunder viser hvor
strengt den slags skal håndhæves:

- *Eksempel:* **Glutenfri.** Alt med hvede, rug, byg, spelt, havre uden
  glutenfri-mærkning.
- *Eksempel:* **Laktosefri** for mejeriprodukter: mælk, yoghurt, fløde, blød
  ost, smøreost. Lagret hård ost er i praksis laktosefri og går an, men vælg
  det mærkede produkt hvis begge dele findes.

**Verificér, gæt ikke — uanset hvilke krav du sætter op.** Bilkas søgning
matcher løst — en søgning på "smør" kan give havregryn. Læs `name` og
`description` på det produkt du vælger, og tjek at kravet faktisk er opfyldt.
Kan du ikke bekræfte det, så læg varen til side og spørg i stedet for at
gætte.

Præferencer, som må vige for pris og tilgængelighed (også eksempler):

- **Økologisk** foretrækkes klart — søg `"<vare> øko"` først.
- **Plantetungt**, men ikke veganer: tofu og plantepostej ja, men også ost,
  yoghurt og feta.
- Faste varer, der altid skal genkøbes uden at blive spurgt om — fx
  husholdningsartikler eller noget et husstandsmedlem bruger fast.

## Fremgangsmåde

1. **Søg pr. vare.** `search_products` med `in_stock_only=True`. Tilføj "øko"
   i søgeordet når det giver mening.
2. **Vælg bevidst.** Første træffer er ikke automatisk den rigtige. Tjek
   kostkravene, og brug `sort="unit_price"` når du sammenligner samme slags
   vare — enhedspris afslører at det store brød ofte er billigere pr. kilo.
   `--sort unit_price` sammenligner kun varer med samme enhed.
3. **Læg i kurven.** `add_to_basket` lægger *oveni* det der ligger i forvejen;
   `set_basket_quantity` sætter et præcist antal. Ved hele lister er
   `add_shopping_list` hurtigere, men den vælger bedste træffer selv — så
   gennemgå bagefter hvad den valgte, især mod kostkravene.
4. **Vis kurven.** Kald `get_basket` og fortæl hvad der kom i, og hvad totalen
   blev. Nævn det hvis noget er udsolgt.
5. **Stop der.** Bestil ikke af dig selv.

## Bestilling

`checkout` bruger det gemte betalingskort. Rigtige penge.

- Kald den **aldrig** uden at brugeren udtrykkeligt har bedt om at bestille.
  "Læg det i kurven" er ikke en bestilling.
- Vis totalen og leveringstiden, og få et klart ja, før du sætter
  `confirm=True`.
- Serveren nægter desuden at bestille med mindre `BILKA_ALLOW_CHECKOUT=1` er
  sat. Bliver den afvist på det, så sig det — forsøg ikke at omgå det.

## Godt at vide

- Kurven kan sagtens indeholde varer fra tidligere. Læs den før du lægger til,
  så du ikke dublerer.
- **Pakkeservice og leveringsgebyr** står som varelinjer i kurven under
  "Services". De er ikke noget du har lagt i — tæl dem ikke med som varer.
- Leveringen er hjemmelevering. Er der ingen leveringstid valgt, så nævn det,
  hvis brugeren er på vej til at bestille — `delivery_dates` viser de ledige.
- Priser vises i kroner. Er en pris påfaldende lav, er det tit stykpris på noget
  småt, ikke et tilbud.
- Søgning virker uden login. Sker der en loginfejl, er det kurven og ordrerne
  der fejler, ikke søgningen — sig hvad der gik galt frem for at prøve igen i
  ring.

## Tonen

Kort og konkret. Sig hvad du lagde i kurven, hvad det kostede, og hvad du var
i tvivl om. Lange lister af alternativer er sjældent til gavn — vælg, og
begrund kort hvis valget ikke er oplagt.
