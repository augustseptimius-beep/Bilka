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
   loginID=<email>  password=<kodeord>  targetEnv=jssdk
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

## 3. Iposen (kurv, ordrer, levering)

Base: `https://api.bilkatogo.dk/api/`. Alle kald tager `?u=w`.
API'et er versioneret pr. endpoint — samme kald findes ikke nødvendigvis
i alle versioner, så brug den version frontenden bruger.

### Svarformat

```json
{"eid": -1, "uid": 12345, "msg": null, ...}
```

`eid = -1` betyder OK. Positive værdier er fejl:

| eid | Betydning |
|---|---|
| 310 | Leveringstid nulstillet |
| 312 | Under minimumskøb |
| 401 | Ikke logget ind |
| 428 | Blokerede varer i kurven |
| 6001 | Over maks. antal |
| -4 | Tilbudsgrænse nået |

### Kurv

| Endpoint | Version | Metode | Parametre |
|---|---|---|---|
| `Cart` | v6 | GET | `basketguid`, `without_cache`, `extra=deliveryAddress,deliveryDate` |
| `ChangeLineCount` | v6 | GET | `productId`, `count`, `fullCart` |
| `ChangeLinesCount` | v6 | POST | body med flere linjer |
| `EmptyCart` | v6 | GET | `extra` |
| `BasketGUID2Cart` | v3 | GET | `basketguid` |
| `voucher` | v6 | POST/DELETE | `voucher_code`, `fullCart` |

**`count` er en relativ ændring, ikke et absolut antal.** `count=2` lægger
to mere i kurven; `count=-1` fjerner én. Skal du sætte et bestemt antal, må
du selv læse kurven først og regne forskellen ud (det gør `set_quantity`).

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
  `ACCESS_DENIED` før routing, så man kan ikke gætte endpoints ved at probe.
- Priser er i øre overalt.
- `count` på `ChangeLineCount` er relativ (se ovenfor).
- Frontenden sender basketændringer gennem en kø med retry, fordi endpointet
  af og til timer ud. Klienten her sætter derfor en eksplicit timeout.
- `withCredentials` er påkrævet — cookien bærer sessionen, JWT'en alene er
  ikke nok.
