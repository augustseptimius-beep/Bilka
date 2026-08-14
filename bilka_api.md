# Bilka To Go - API-noter

Reverse engineered fra Nuxt-frontenden på `https://www.bilkatogo.dk`
(bundles under `/_nuxt/*.js`, modulet der hedder `iposen-sdk.js` internt).
Intet af dette er officielt dokumenteret, så det kan ændre sig uden varsel.

## Systemerne bag

Bilka To Go består af tre uafhængige backends:

| Funktion | Backend | Auth |
|---|---|---|
| Varesøgning | Algolia | Public search key |
| Login | Gigya (SAP Customer Data Cloud) | API-nøgle + brugerens kodeord |
| Kurv, ordrer, levering | Iposen (`api.bilkatogo.dk`, PHP) | JWT → PHP-sessionscookie |

Konstanterne ligger i klartekst i frontendens bundle som `NUXT_ENV_*`.

## 1. Søgning (Algolia)

```
POST https://F9VBJLR1BK-dsn.algolia.net/1/indexes/*/queries
X-Algolia-Application-Id: F9VBJLR1BK
X-Algolia-API-Key: 1deaf41c87e729779f7695c00f190cc9
```

Indeks:

| Indeks | Brug |
|---|---|
| `prod_BILKATOGO_PRODUCTS` | Hele kataloget, ~36.900 varer |
| `prod_r_BILKATOGO_PRODUCT_pricesort` | Sorteret efter pris |
| `prod_r_BILKATOGO_PRODUCT_uompricesort` | Sorteret efter enhedspris |
| `prod_qs_BILKATOGO_PRODUCT` | Query suggestions |
| `prod_BILKATOGO_BOUGHTBY` | Købshistorik pr. bruger |
| `prod_BILKATOGO_FAVORITE` | Favoritter |

Nyttige felter på en vare:

| Felt | Betydning |
|---|---|
| `objectID` / `id` | Produkt-id — det Iposen vil have |
| `name`, `brand`, `netcontent` | Navn, mærke, størrelse |
| `price`, `sales_price` | Pris i **øre** (1105 = 11,05 kr) |
| `cpOfferPrice`, `cpOfferTitle` | Tilbudspris og -tekst |
| `unitOfMeasurePrice` + `...Units` | Enhedspris, fx pr. `L.` |
| `isInStock` | 1/0 |
| `pant`, `ageCode` | Pant, aldersgrænse (>0 = aldersbegrænset) |
| `searchHierachy`, `categories` | Kategoristi |

Alle beløb i hele API'et er i øre.

## 2. Login

Tre trin. Frontenden gør præcis det samme.

```
1) POST https://accounts.eu1.gigya.com/accounts.login
   apiKey=3_tA6BbV434FQqN73HnUG1KA3qFv8KiG4OqLu9eWPh7sKRqRizH5Vfv5Larmgrb4I2
   loginID=<email>  password=<kodeord>
   -> sessionInfo.cookieValue  (login_token)

2) POST https://accounts.eu1.gigya.com/accounts.getJWT
   ?apiKey=...&login_token=<token>&expiration=86400
   -> id_token  (JWT)

3) POST https://api.bilkatogo.dk/api/auth/LoginJWT?u=w
   Header: jwt_token: <JWT>
   -> sætter PHP-sessionscookie
```

Derefter sendes både sessionscookien og headeren `jwt_token` med på alle
kald. Sessionen udløber, og svaret bliver da `ACCESS_DENIED` / `eid: 401` —
så skal trin 1-3 køres igen.

**Send ikke `targetEnv` i trin 1.** Frontenden kører i browseren og bruger
`targetEnv=jssdk`, men så returnerer Gigya et `sessionInfo.login_token`
beregnet til JS-SDK'ets egen cookie-session, og `getJWT` afviser det med
`403005 Unauthorized user`. Uden `targetEnv` kommer der i stedet et
`sessionInfo.cookieValue`, og *det* accepterer `getJWT`. `targetEnv=mobile`
giver `sessionToken`/`sessionSecret`, som også afvises (403005 via
`login_token`, 403007 via `oauth_token`).

Trin 3 kvitterer med `{"msg": "authenticated", "eid": 200, "uid": ...}`.

## 3. Iposen (kurv, ordrer, levering)

Base: `https://api.bilkatogo.dk/api/`. Alle kald tager `?u=w`.
API'et er versioneret pr. endpoint — samme kald findes ikke nødvendigvis
i alle versioner, så brug den version frontenden bruger.

### Svarformat

```json
{"eid": -1, "uid": 12345, "msg": null, ...}
```

`eid = -1` betyder OK, og `eid = 200` betyder "authenticated". **Positive
værdier er ikke automatisk fejl.** Et almindeligt `Cart`-kald svarer rutinemæssigt
`eid: 310` og leverer alligevel hele kurven. Behandler man alt over 0 som en
fejl, virker ingenting.

| eid | Betydning | Reel fejl? |
|---|---|---|
| -1 | OK | nej |
| 200 | Authenticated | nej |
| 310 | Leveringstid nulstillet | nej — data følger med |
| 312 | Under minimumskøb | nej — oplysning |
| 315 | Rabatkode utilgængelig | afhænger af kaldet |
| -4 | Tilbudsgrænse nået | oplysning |
| 400, 401, 403, 407 | Afvist / ikke logget ind | ja |
| 428 | Blokerede varer i kurven | ja |
| 500, 501, 503 | Serverfejl | ja |
| 6001 | Over maks. antal | ja |

### Kurv

| Endpoint | Version | Metode | Parametre |
|---|---|---|---|
| `Cart` | v6 | GET | `basketguid`, `without_cache`, `extra=deliveryAddress,deliveryDate` |
| `ChangeLineCount` | v6 | GET | `productId`, `count`, `fullCart` |
| `ChangeLinesCount` | v6 | POST | body med flere linjer |
| `EmptyCart` | v6 | GET | `extra` |
| `BasketGUID2Cart` | v3 | GET | `basketguid` |
| `voucher` | v6 | POST/DELETE | `voucher_code`, `fullCart` |

**`count` er et absolut antal, ikke en ændring.** `count=3` giver tre styk
uanset hvad der lå i kurven i forvejen, og `count=0` fjerner linjen. Vil du
lægge noget *oveni* det eksisterende, skal du selv læse kurven først og
sende summen.

Målt direkte mod API'et med samme vare:

| Sendt | Kurven havde | Kurven fik |
|---|---|---|
| `count=4` | 0 | 4 |
| `count=2` | 4 | 2 |
| `count=7` | 2 | 7 |
| `count=0` | 7 | 0 |

Frontendens kode inviterer til at læse det forkert: dens store-action
beregner en `quantityAdded` som `ønsket - nuværende`, men den værdi bruges
kun til analytics. Det der faktisk sendes videre til `ChangeLineCount` er
det absolutte antal.

### Kurvens struktur

`Cart` returnerer ikke en flad liste. Varerne ligger tre niveauer nede:

```
lines[]                     kategorigruppe: {headline, type, lines[]}
  └── lines[]               {discounts, orderlines[]}
        └── orderlines[]    {quantity, unitprice, amount, product{...}}
```

Produkt-id'et er `orderlines[].product.objectID` — det samme id som Algolia
bruger. Gebyrer (pakkeservice, leveringsgebyr) ligger som almindelige linjer
i gruppen med `headline: "Services"`, så de skal sorteres fra, hvis man kun
vil se dagligvarer.

Totalerne står i `stat`, ikke i linjerne:

| Felt | Betydning |
|---|---|
| `price` | Alt i alt, inkl. gebyrer |
| `prod_price` | Kun varer |
| `price_no_promo` | Før rabat |
| `promo` | Rabat |
| `amount` / `prod_amount` | Antal stk. med / uden gebyrer |
| `packing`, `delivery_price` | Pakkeservice og levering |
| `oos` | Udsolgte varer i kurven |
| `specifications[]` | Gebyrerne som `{text, value}` |

Leveringstiden ligger i `deliveryDate` som et objekt med `deliveryDate`,
`intervalStart`/`intervalEnd` og en færdig `delivery_message`.

### Ordrer

| Endpoint | Version | Metode | Parametre |
|---|---|---|---|
| `OrderHistory` | v7 | POST | `limit`, `offset`, `muah`, `ordertype` |
| `OrderDetails` | v7 | GET | `orderId` |
| `CopyOrder` | v6 | GET | `orderId`, `without_cache`, `extra` |

### Levering

| Endpoint | Version | Metode | Parametre |
|---|---|---|---|
| `AvailableDeliveryDates` | v3 | GET | - |
| `SetDeliveryDate` | v3 | GET | `deliveryDate`, `intervalStart`, `intervalEnd` |
| `AvailableDeliveryAddresses` | v6 | GET | `orderByZipcode` |
| `SetDeliveryAddress` | v6 | GET | `id`, `zipcode`, `dawa_uid`, `recipient_name`, `street` |
| `GetDeliveryAddress` | v3 | GET | - |
| `GetDeliveryDate` | v3 | GET | - |

### Profil og favoritter

| Endpoint | Version | Metode | Parametre |
|---|---|---|---|
| `Profile` | v3 | GET | - |
| `GetFavs` | v3 | POST | `grouped` |
| `AddFav` / `RemoveFav` | v3 | POST | `productId`, `enterprise` |
| `Settings` | v4 | GET | - |
| `GetReplacementSettings` | v3 | GET | - |
| `SetAllReplacementSettings` | v3 | GET | `value` (0=ingen, 1=lignende, 7=økologisk) |

### Betaling

| Endpoint | Base | Metode | Parametre |
|---|---|---|---|
| `GotoPayment` | shop/v3 | POST | `sum`, `amount` (form-encoded) |
| `CheckOut` | shop/v3 | POST | `paymentMethod`, `amount` (form-encoded) |
| `PaymentMethods` | shop/v3 | GET | - |
| `initiate` | payment | POST | `accept_url`, `cancel_url`, evt. `giftcard` |
| `options` | payment | POST | `primary`, `secondary` |
| `status` | payment | GET | `order_id` |

Selve kortbetalingen ligger hos Nets (`checkout.dibspayment.eu`), ikke i
Iposen. `CheckOut` med `paymentMethod: 8` bruger det gemte kort på kontoen.

### Øvrige

| Endpoint | Base |
|---|---|
| `ConsumerFacingHierarchy` | `/api/shop/` — hele varetræet |
| `Initialize` | `/api/structure/` |
| `Initialize` | `/api/notification/` |
| `Zipcode/{zip}/{land}` | `/api/address/` |
| `CheckZipcode` | `/api/address/` — `zipcode` |
| `GetOptions` / `SetOption` | `/api/packaging/v2/` — emballagevalg |
| `Deliverypoints`, `delivery` | `/api/comment/` |

## Faldgruber

- Ukendte ruter svarer `NOOOO` med HTTP 200. Alt under `/api/shop/` svarer
  `ACCESS_DENIED` før routing, så man kan ikke gætte endpoints ved at probe —
  et gyldigt og et opdigtet endpoint ser ens ud, indtil man er logget ind.
- Priser er i øre overalt.
- `count` på `ChangeLineCount` er absolut (se ovenfor).
- `eid > 0` er ikke ensbetydende med fejl (se tabellen ovenfor).
- Drop `targetEnv` i Gigya-login, ellers afviser `getJWT`.
- Frontenden sender basketændringer gennem en kø med retry, fordi endpointet
  af og til timer ud. Klienten her sætter derfor en eksplicit timeout.
- `withCredentials` er påkrævet — cookien bærer sessionen, JWT'en alene er
  ikke nok.
