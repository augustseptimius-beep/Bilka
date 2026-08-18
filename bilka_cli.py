#!/usr/bin/env python3
"""Bilka To Go CLI - handel ind hos bilkatogo.dk fra kommandolinjen.

Alt klientlogik bor i denne fil. server.py eksponerer den blot som MCP-tools.

Arkitektur (reverse engineered fra www.bilkatogo.dk):

  Sog     -> Algolia (prod_BILKATOGO_PRODUCTS)
  Login   -> Gigya (accounts.eu1.gigya.com) -> JWT -> Iposen LoginJWT -> PHP session
  Kurv    -> https://api.bilkatogo.dk/api/shop/v{3..7}/

Se bilka_api.md for den fulde endpoint-dokumentation.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import requests

# --------------------------------------------------------------------------
# Konstanter aflaest fra frontendens Nuxt-bundle (NUXT_ENV_*)
# --------------------------------------------------------------------------

ALGOLIA_APP_ID = "F9VBJLR1BK"
ALGOLIA_SEARCH_KEY = "1deaf41c87e729779f7695c00f190cc9"
ALGOLIA_INDEX = "prod_BILKATOGO_PRODUCTS"
ALGOLIA_INDEX_PRICE_ASC = "prod_r_BILKATOGO_PRODUCT_pricesort"
ALGOLIA_INDEX_UNIT_PRICE_ASC = "prod_r_BILKATOGO_PRODUCT_uompricesort"
ALGOLIA_URL = f"https://{ALGOLIA_APP_ID}-dsn.algolia.net/1/indexes/*/queries"

GIGYA_BASE_URL = "https://accounts.eu1.gigya.com"
GIGYA_API_KEY = "3_tA6BbV434FQqN73HnUG1KA3qFv8KiG4OqLu9eWPh7sKRqRizH5Vfv5Larmgrb4I2"

API_BASE = "https://api.bilkatogo.dk"

# Iposen svarer med eid=-1 ved succes og eid=200 ved "authenticated".
# Positive vaerdier er ikke automatisk fejl: 310 (RESET_DELIVERYTIME) og
# 312 (MINIMUM_BUY) leveres sammen med gyldige data og er kun oplysninger.
# Kun koderne herunder betyder at kaldet reelt mislykkedes.
EID_OK = -1
EID_AUTHENTICATED = 200
EID_HARD_ERRORS = {
    400,   # BAD_REQUEST
    401,   # UNAUTHORIZED
    402,   # PAYMENT_REQUIRED
    403,   # FORBIDDEN
    406,   # NOT_ACCEPTABLE
    407,   # AUTHENTICATION_REQUIRED
    409,   # CONFLICT
    428,   # BLOCKED_PRODUCTS
    500,   # INTERNAL_SERVER_ERROR
    501,   # NOT_IMPLEMENTED
    503,   # SERVICE_UNAVAILABLE
    6001,  # QUANTITY_LIMIT
}

DEFAULT_TIMEOUT = 30
SESSION_TTL = 3600  # sekunder vi genbruger en session for re-login

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
)

# Felter vi henter fra Algolia. "*" ville virke, men listen holder svaret lille.
PRODUCT_FIELDS = [
    "objectID", "id", "name", "productName", "brand", "description",
    "price", "sales_price", "unitOfMeasurePrice", "unitOfMeasurePriceUnits",
    "netcontent", "uom", "units", "isInStock", "pant", "ageCode",
    "isInOffer", "cpOffer", "cpOfferPrice", "cpOfferTitle", "cpDiscount",
    "is_multibuy", "multibuy_offer_description", "searchHierachy",
    "categories", "countryOfOrigin", "gtin",
]


class BilkaError(RuntimeError):
    """Fejl fra Bilka/Iposen-API'et eller fra login."""


# --------------------------------------------------------------------------
# Hjaelpere
# --------------------------------------------------------------------------

def ore_to_kr(value: Any) -> float | None:
    """Iposen og Algolia regner i ore. 1105 -> 11.05"""
    if value is None or value == "":
        return None
    try:
        return round(int(value) / 100, 2)
    except (TypeError, ValueError):
        return None


def kr(value: Any) -> str:
    v = ore_to_kr(value)
    return "-" if v is None else f"{v:.2f}".replace(".", ",")


def _config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config")
    d = Path(base) / "bilka-cli"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _truthy(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y", "ja"}


# --------------------------------------------------------------------------
# Produktmodel
# --------------------------------------------------------------------------

@dataclass
class Product:
    id: str
    name: str
    brand: str = ""
    price: int | None = None            # ore, normalpris
    offer_price: int | None = None      # ore, tilbudspris hvis aktiv
    unit_price: int | None = None       # ore pr. enhed
    unit_price_unit: str = ""
    netcontent: str = ""
    in_stock: bool = True
    offer_title: str = ""
    deposit: bool = False               # pant
    age_code: int = 0
    category: str = ""
    raw: dict = field(default_factory=dict, repr=False)

    @classmethod
    def from_hit(cls, hit: dict) -> "Product":
        offers = hit.get("isInOffer") or []
        sales, normal = hit.get("sales_price"), hit.get("price")
        # De prissorterede replika-indekser leverer kun sales_price.
        if not normal:
            normal = sales
        offer_price = hit.get("cpOfferPrice") or None
        # sales_price afviger fra price naar der koerer et tilbud
        if not offer_price and sales and normal and sales != normal:
            offer_price = sales
        hierarchy = hit.get("searchHierachy") or []
        return cls(
            id=str(hit.get("objectID") or hit.get("id") or ""),
            name=hit.get("name") or hit.get("productName") or "",
            brand=hit.get("brand") or "",
            price=normal,
            offer_price=offer_price,
            unit_price=hit.get("unitOfMeasurePrice"),
            unit_price_unit=hit.get("unitOfMeasurePriceUnits") or "",
            netcontent=hit.get("netcontent") or "",
            in_stock=bool(hit.get("isInStock", 1)),
            offer_title=hit.get("cpOfferTitle") or (
                ", ".join(str(o) for o in offers) if offers else ""
            ),
            deposit=bool(hit.get("pant")),
            age_code=int(hit.get("ageCode") or 0),
            category=hierarchy[-1] if hierarchy else "",
            raw=hit,
        )

    @property
    def effective_price(self) -> int | None:
        return self.offer_price or self.price

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "brand": self.brand,
            "price_kr": ore_to_kr(self.price),
            "offer_price_kr": ore_to_kr(self.offer_price),
            "effective_price_kr": ore_to_kr(self.effective_price),
            "unit_price_kr": ore_to_kr(self.unit_price),
            "unit_price_unit": self.unit_price_unit,
            "netcontent": self.netcontent,
            "in_stock": self.in_stock,
            "offer": self.offer_title,
            "deposit": self.deposit,
            "age_restricted": self.age_code > 0,
            "category": self.category,
        }

    def line(self) -> str:
        price = kr(self.effective_price)
        tag = " [TILBUD]" if self.offer_price else ""
        stock = "" if self.in_stock else " [UDSOLGT]"
        unit = ""
        if self.unit_price:
            unit = f"  ({kr(self.unit_price)} kr/{self.unit_price_unit})"
        brand = f"{self.brand} - " if self.brand else ""
        size = f", {self.netcontent}" if self.netcontent else ""
        return (
            f"{self.id:>8}  {price:>8} kr  {brand}{self.name}{size}"
            f"{unit}{tag}{stock}"
        )


# --------------------------------------------------------------------------
# Klient
# --------------------------------------------------------------------------

class BilkaClient:
    """Klient til bilkatogo.dk.

    Sogning virker uden login. Alt der roerer kurv, ordrer og profil kraever
    login med et Bilka/Salling-login (samme som pa hjemmesiden).
    """

    def __init__(
        self,
        username: str | None = None,
        password: str | None = None,
        session_file: Path | None = None,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> None:
        self.username = username or os.environ.get("BILKA_USERNAME") or ""
        self.password = password or os.environ.get("BILKA_PASSWORD") or ""
        self.timeout = timeout
        self.session_file = session_file or (_config_dir() / "session.json")
        self._jwt: str | None = None
        self._logged_in = False

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://www.bilkatogo.dk",
            "Referer": "https://www.bilkatogo.dk/",
        })
        self._load_session()

    # ---------------------------------------------------------------- session

    def _load_session(self) -> None:
        """Genbrug cookies fra en tidligere koersel, sa vi ikke logger ind hver gang."""
        try:
            data = json.loads(self.session_file.read_text())
        except (OSError, ValueError):
            return
        if time.time() - data.get("saved_at", 0) > SESSION_TTL:
            return
        if data.get("username") and data["username"] != self.username:
            return
        for name, value in (data.get("cookies") or {}).items():
            self.session.cookies.set(name, value, domain="api.bilkatogo.dk")
        self._jwt = data.get("jwt")
        self._logged_in = bool(data.get("cookies"))

    def _save_session(self) -> None:
        payload = {
            "saved_at": time.time(),
            "username": self.username,
            "jwt": self._jwt,
            "cookies": {c.name: c.value for c in self.session.cookies},
        }
        # Filen indeholder en levende JWT og sessionscookie. Den skal
        # oprettes med 0600 fra starten - skriver man foerst og strammer
        # bagefter, ligger indholdet aabent i vinduet imellem.
        try:
            fd = os.open(
                self.session_file,
                os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
                0o600,
            )
            try:
                with os.fdopen(fd, "w") as fh:
                    json.dump(payload, fh)
            finally:
                # Havde filen allerede loesere rettigheder, retter O_CREAT
                # dem ikke - saet dem eksplicit.
                try:
                    self.session_file.chmod(0o600)
                except OSError:
                    pass
        except OSError:
            pass  # cache er en optimering, ikke et krav

    def forget_session(self) -> None:
        self.session.cookies.clear()
        self._jwt = None
        self._logged_in = False
        self.session_file.unlink(missing_ok=True)

    # ------------------------------------------------------------------ login

    def login(self, force: bool = False) -> None:
        """Gigya-login -> JWT -> Iposen-session.

        1. accounts.login          -> login_token
        2. accounts.getJWT         -> id_token (JWT)
        3. /api/auth/LoginJWT      -> PHP-sessionscookie hos Iposen
        """
        if self._logged_in and not force:
            return
        if not self.username or not self.password:
            raise BilkaError(
                "Manglende login. Saet BILKA_USERNAME og BILKA_PASSWORD "
                "(eller brug -u/-p)."
            )

        # 1) Gigya login
        r = self.session.post(
            f"{GIGYA_BASE_URL}/accounts.login",
            # Ingen targetEnv med vilje. Med targetEnv=jssdk giver Gigya et
            # login_token beregnet til browseren, og getJWT afviser det med
            # 403005. Uden targetEnv kommer der et cookieValue, som getJWT
            # accepterer.
            data={
                "apiKey": GIGYA_API_KEY,
                "loginID": self.username,
                "password": self.password,
                "includeUserInfo": "true",
            },
            timeout=self.timeout,
        )
        body = r.json()
        if body.get("errorCode"):
            raise BilkaError(
                f"Gigya-login fejlede: {body.get('errorMessage')} "
                f"({body.get('errorDetails') or body.get('errorCode')})"
            )
        # Med targetEnv=jssdk hedder feltet login_token; i andre modes
        # hedder det cookieValue. Tag det der er der.
        session_info = body.get("sessionInfo") or {}
        login_token = (
            session_info.get("login_token") or session_info.get("cookieValue")
        )
        if not login_token:
            raise BilkaError(
                f"Gigya returnerede intet login_token (felter: "
                f"{sorted(session_info)})"
            )

        # 2) Veksl til JWT
        r = self.session.post(
            f"{GIGYA_BASE_URL}/accounts.getJWT",
            params={
                "apiKey": GIGYA_API_KEY,
                "login_token": login_token,
                "expiration": "86400",
                "httpStatusCodes": "true",
            },
            timeout=self.timeout,
        )
        body = r.json()
        jwt = body.get("id_token")
        if not jwt:
            raise BilkaError(f"Kunne ikke hente JWT: {body.get('errorMessage')}")
        self._jwt = jwt

        # 3) Byt JWT til en Iposen-session
        r = self.session.post(
            f"{API_BASE}/api/auth/LoginJWT",
            params={"u": "w"},
            headers={"jwt_token": jwt},
            timeout=self.timeout,
        )
        if r.status_code != 200:
            raise BilkaError(f"LoginJWT fejlede: HTTP {r.status_code} {r.text[:200]}")
        data = r.json() if r.content else {}
        # LoginJWT kvitterer med eid=200 / msg="authenticated" ved succes.
        if int(data.get("eid", EID_OK)) in EID_HARD_ERRORS:
            raise BilkaError(f"LoginJWT afvist: {data.get('msg')}")

        self._logged_in = True
        self._save_session()

    def logout(self) -> None:
        if self._logged_in:
            try:
                self.session.post(
                    f"{API_BASE}/api/auth/Logout",
                    params={"u": "w"}, timeout=self.timeout,
                )
            except requests.RequestException:
                pass
        self.forget_session()

    # ------------------------------------------------------------- HTTP-kerne

    def _request(
        self,
        version: str,
        endpoint: str,
        method: str = "GET",
        params: dict | None = None,
        data: Any = None,
        json_body: Any = None,
        require_login: bool = True,
        _retry: bool = True,
    ) -> dict:
        """Kald et Iposen-endpoint. version er fx 'shop/v6' eller 'auth'."""
        if require_login:
            self.login()

        params = dict(params or {})
        params.setdefault("u", "w")
        headers = {"jwt_token": self._jwt} if self._jwt else {}

        url = f"{API_BASE}/api/{version.strip('/')}/{endpoint.lstrip('/')}"
        try:
            r = self.session.request(
                method, url, params=params, data=data, json=json_body,
                headers=headers, timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise BilkaError(f"Netvaerksfejl mod {endpoint}: {exc}") from exc

        # Sessionen kan udloebe midt i det hele -> log ind igen og proev en gang til.
        if r.status_code in (401, 403) and require_login and _retry:
            self._logged_in = False
            self.login(force=True)
            return self._request(
                version, endpoint, method, params, data, json_body,
                require_login, _retry=False,
            )

        if r.status_code >= 400:
            raise BilkaError(f"{endpoint}: HTTP {r.status_code} {r.text[:200]}")

        if not r.content:
            return {}
        try:
            body = r.json()
        except ValueError:
            raise BilkaError(f"{endpoint}: uventet svar {r.text[:200]}") from None

        if isinstance(body, dict):
            try:
                eid = int(body.get("eid"))
            except (TypeError, ValueError):
                eid = None
            if eid in EID_HARD_ERRORS:
                # Sessionen kan vaere udloebet - log ind igen og proev en gang til.
                if eid in (401, 403, 407) and require_login and _retry:
                    self._logged_in = False
                    self.login(force=True)
                    return self._request(
                        version, endpoint, method, params, data, json_body,
                        require_login, _retry=False,
                    )
                raise BilkaError(
                    f"{endpoint}: {body.get('msg') or 'ukendt fejl'} "
                    f"(eid={eid}, code={body.get('code')})"
                )
        return body

    # ------------------------------------------------------------------- sog

    def search(
        self,
        query: str,
        limit: int = 20,
        page: int = 0,
        sort: str = "relevance",
        only_offers: bool = False,
        in_stock_only: bool = False,
        filters: str | None = None,
    ) -> list[Product]:
        """Sog i varekataloget via Algolia. Kraever ikke login.

        Bilkas prissorterede indekser er replikaer der har smidt baade
        ``price`` og ``unitOfMeasurePrice`` vaek, sa de kan hverken vise
        eller filtrere pa pris. Vi henter derfor altid fra hovedindekset og
        sorterer selv over de mest relevante traeffer. Det giver samtidig
        "billigst blandt de relevante varer" frem for "billigste vare i hele
        kataloget der tilfaeldigvis matcher ordet".
        """
        clauses = [filters] if filters else []
        if only_offers:
            clauses.append("cpOffer=1")
        if in_stock_only:
            clauses.append("isInStock=1")

        # Ved sortering henter vi et bredere felt at sortere indenfor. Det
        # maa ikke blive for bredt: Algolia matcher loest, sa de nederste
        # traeffer har ofte kun perifert med soegningen at goere.
        fetch = limit if sort == "relevance" else min(max(limit * 4, 40), 200)

        params: dict[str, Any] = {
            "query": query,
            "hitsPerPage": fetch,
            "page": page,
            "attributesToRetrieve": json.dumps(PRODUCT_FIELDS),
        }
        if clauses:
            params["filters"] = " AND ".join(f"({c})" for c in clauses)

        products = self._algolia(ALGOLIA_INDEX, params)

        if sort == "price":
            products = [p for p in products if p.effective_price]
            products.sort(key=lambda p: p.effective_price)
            products = products[:limit]
        elif sort == "unit_price":
            # Enhedspriser kan kun sammenlignes indbyrdes hvis de har samme
            # enhed - 0,64 kr/meter er ikke billigere end 9,95 kr/kg. Vi
            # holder os derfor til den enhed flest af traefferne bruger.
            priced = [p for p in products if p.unit_price]
            if priced:
                units = Counter(p.unit_price_unit for p in priced)
                dominant = units.most_common(1)[0][0]
                priced = [p for p in priced if p.unit_price_unit == dominant]
                priced.sort(key=lambda p: p.unit_price)
            products = priced[:limit]

        return products

    def get_product(self, product_id: str | int) -> Product | None:
        """Slå et enkelt produkt op på id."""
        hits = self._algolia(ALGOLIA_INDEX, {
            "query": "",
            "hitsPerPage": 1,
            "filters": f"objectID:{product_id}",
            "attributesToRetrieve": json.dumps(["*"]),
        })
        return hits[0] if hits else None

    def get_products(self, ids: Iterable[str | int]) -> dict[str, Product]:
        """Slå flere produkter op på en gang."""
        ids = [str(i) for i in ids]
        if not ids:
            return {}
        found: dict[str, Product] = {}
        # Algolia-filtre bliver tunge i store bundter - del dem op.
        for i in range(0, len(ids), 50):
            chunk = ids[i:i + 50]
            hits = self._algolia(ALGOLIA_INDEX, {
                "query": "",
                "hitsPerPage": len(chunk),
                "filters": " OR ".join(f"objectID:{pid}" for pid in chunk),
                "attributesToRetrieve": json.dumps(PRODUCT_FIELDS),
            })
            found.update({p.id: p for p in hits})
        return found

    def _algolia(self, index: str, params: dict) -> list[Product]:
        payload = {"requests": [{
            "indexName": index,
            "params": "&".join(
                f"{k}={requests.utils.quote(str(v), safe='')}"
                for k, v in params.items()
            ),
        }]}
        try:
            r = self.session.post(
                ALGOLIA_URL,
                headers={
                    "X-Algolia-Application-Id": ALGOLIA_APP_ID,
                    "X-Algolia-API-Key": ALGOLIA_SEARCH_KEY,
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=self.timeout,
            )
            r.raise_for_status()
            body = r.json()
        except requests.RequestException as exc:
            raise BilkaError(f"Sogning fejlede: {exc}") from exc
        if "results" not in body:
            raise BilkaError(f"Sogning fejlede: {body.get('message', body)}")
        return [Product.from_hit(h) for h in body["results"][0].get("hits", [])]

    # ------------------------------------------------------------------ kurv

    def get_basket(self, fresh: bool = True) -> dict:
        """Hent kurven. Returnerer det raa Iposen-svar."""
        params: dict[str, Any] = {"extra": "deliveryAddress,deliveryDate"}
        if fresh:
            params["without_cache"] = 1
        return self._request("shop/v6", "Cart", params=params)

    def basket_lines(self, include_services: bool = True) -> list[dict]:
        """Kurvens linjer fladet ud.

        Iposen leverer kurven i tre lag: kategorigrupper med en overskrift,
        derunder poster, og i hver post en liste af ``orderlines``. Gebyrer
        som pakkeservice og levering ligger i gruppen "Services" sammen med
        varerne, sa de kan sorteres fra med include_services=False.
        """
        return self._parse_lines(self.get_basket(), include_services)

    @staticmethod
    def _parse_lines(basket: dict, include_services: bool = True) -> list[dict]:
        out: list[dict] = []
        for group in basket.get("lines") or []:
            headline = group.get("headline") or ""
            is_service = headline.strip().lower() == "services"
            if is_service and not include_services:
                continue
            for entry in group.get("lines") or []:
                for line in entry.get("orderlines") or []:
                    product = line.get("product") or {}
                    out.append({
                        "id": str(product.get("objectID") or ""),
                        "name": product.get("name") or "",
                        "brand": product.get("brand") or "",
                        "quantity": line.get("quantity") or 0,
                        "unit_price_kr": ore_to_kr(line.get("unitprice")),
                        "total_kr": ore_to_kr(line.get("amount")),
                        "group": headline,
                        "is_service": is_service,
                        "unavailable": line.get("unavailable_reason") or None,
                        "raw": line,
                    })
        return out

    def basket_summary(self) -> dict:
        """Kurvens total og antal varer."""
        return self._parse_summary(self.get_basket())

    @staticmethod
    def _parse_summary(basket: dict) -> dict:
        stat = basket.get("stat") or {}
        delivery = basket.get("deliveryDate") or {}
        return {
            "total_kr": ore_to_kr(stat.get("price")),
            "products_kr": ore_to_kr(stat.get("prod_price")),
            "total_before_discount_kr": ore_to_kr(stat.get("price_no_promo")),
            "discount_kr": ore_to_kr(stat.get("promo")),
            "deposit_kr": ore_to_kr(stat.get("deposit")),
            "packing_kr": ore_to_kr(stat.get("packing")),
            "delivery_kr": ore_to_kr(stat.get("delivery_price")),
            "vat_kr": ore_to_kr(stat.get("price_vat")),
            # amount taeller gebyrer med, prod_amount er kun varer.
            "quantity": stat.get("prod_amount"),
            "quantity_incl_services": stat.get("amount"),
            "has_soldout": bool(stat.get("oos")),
            "has_replacements": bool(stat.get("has_replacements")),
            "minimum_left_kr": ore_to_kr(stat.get("minimum_left")),
            "vouchers": stat.get("vouchers") or [],
            "delivery_date": delivery.get("deliveryDate"),
            "delivery_message": delivery.get("delivery_message"),
            "fees": [
                {"text": s.get("text"), "kr": ore_to_kr(s.get("value"))}
                for s in (stat.get("specifications") or [])
            ],
        }

    def change_line(self, product_id: str | int, count: int) -> dict:
        """Saet antallet af en vare i kurven.

        ``count`` er et **absolut** antal, ikke en aendring: count=3 giver tre
        styk uanset hvad der la i kurven i forvejen, og count=0 fjerner
        linjen.
        """
        return self._request("shop/v6", "ChangeLineCount", params={
            "productId": product_id,
            "count": max(0, int(count)),
            "fullCart": 0,
        })

    def set_quantity(self, product_id: str | int, quantity: int) -> dict:
        """Saet et praecist antal af en vare."""
        return self.change_line(product_id, quantity)

    def add(self, product_id: str | int, quantity: int = 1) -> dict:
        """Laeg quantity styk oveni det der allerede ligger i kurven."""
        if quantity <= 0:
            raise BilkaError("quantity skal vaere positiv - brug remove() i stedet")
        return self.change_line(
            product_id, self.quantity_in_basket(product_id) + quantity
        )

    def remove(self, product_id: str | int, quantity: int | None = None) -> dict:
        """Fjern varen. Uden quantity fjernes hele linjen."""
        if quantity is None:
            return self.change_line(product_id, 0)
        current = self.quantity_in_basket(product_id)
        if current <= 0:
            return {"eid": EID_OK, "msg": "Varen er ikke i kurven"}
        return self.change_line(product_id, max(0, current - quantity))

    def quantity_in_basket(self, product_id: str | int) -> int:
        pid = str(product_id)
        for line in self.basket_lines():
            if line["id"] == pid:
                try:
                    return int(line["quantity"])
                except (TypeError, ValueError):
                    return 0
        return 0

    def add_many(self, items: dict[str | int, int]) -> list[dict]:
        """Laeg flere varer i kurven. items er {produkt_id: antal}.

        Kurven laeses en gang op front i stedet for en gang pr. vare.
        """
        current = {line["id"]: line["quantity"]
                   for line in self.basket_lines()}
        results = []
        for pid, qty in items.items():
            target = int(current.get(str(pid), 0) or 0) + qty
            try:
                self.change_line(pid, target)
                results.append({"id": str(pid), "quantity": qty,
                                "total": target, "ok": True})
            except BilkaError as exc:
                results.append({"id": str(pid), "quantity": qty,
                                "ok": False, "error": str(exc)})
        return results

    def empty_basket(self) -> dict:
        return self._request("shop/v6", "EmptyCart",
                             params={"extra": "deliveryAddress,deliveryDate"})

    def add_voucher(self, code: str) -> dict:
        return self._request("shop/v6", "voucher", method="POST",
                             params={"voucher_code": code, "fullCart": 1})

    def remove_voucher(self, code: str) -> dict:
        return self._request("shop/v6", "voucher", method="DELETE",
                             params={"voucher_code": code, "fullCart": 1})

    # -------------------------------------------------------------- favoritter

    def favorites(self) -> dict:
        return self._request("shop/v3", "GetFavs", method="POST",
                             params={"grouped": "false"})

    def add_favorite(self, product_id: str | int) -> dict:
        return self._request("shop/v3", "AddFav", method="POST",
                             params={"productId": product_id, "enterprise": "true"})

    def remove_favorite(self, product_id: str | int) -> dict:
        return self._request("shop/v3", "RemoveFav", method="POST",
                             params={"productId": product_id, "enterprise": "true"})

    # ------------------------------------------------------------------ ordrer

    def order_history(self, limit: int = 10, offset: int = 0) -> dict:
        return self._request("shop/v7", "OrderHistory", method="POST", params={
            "limit": limit, "offset": offset, "muah": 1, "ordertype": "dibs,pgw",
        })

    def order_details(self, order_id: str | int) -> dict:
        return self._request("shop/v7", "OrderDetails", params={"orderId": order_id})

    def copy_order(self, order_id: str | int) -> dict:
        """Kopier en tidligere ordre ind i kurven - 'det samme som sidst'."""
        return self._request("shop/v6", "CopyOrder", params={
            "orderId": order_id,
            "without_cache": 1,
            "extra": "deliveryAddress,deliveryDate",
        })

    # ----------------------------------------------------------------- levering

    def delivery_dates(self) -> dict:
        return self._request("shop/v3", "AvailableDeliveryDates")

    def set_delivery_date(self, date: str, start: str, end: str) -> dict:
        return self._request("shop/v3", "SetDeliveryDate", params={
            "deliveryDate": date, "intervalStart": start, "intervalEnd": end,
        })

    def delivery_addresses(self, order_by_zipcode: str | None = None) -> dict:
        params = {"orderByZipcode": order_by_zipcode} if order_by_zipcode else {}
        return self._request("shop/v6", "AvailableDeliveryAddresses", params=params)

    def current_delivery(self) -> dict:
        return {
            "address": self._request("shop/v3", "GetDeliveryAddress"),
            "date": self._request("shop/v3", "GetDeliveryDate"),
        }

    # ------------------------------------------------------------------ profil

    def profile(self) -> dict:
        return self._request("shop/v3", "Profile")

    def payment_methods(self) -> dict:
        return self._request("shop/v3", "PaymentMethods")

    # ---------------------------------------------------------------- checkout

    def checkout(self, confirm: bool = False) -> dict:
        """Send ordren afsted. Koster rigtige penge.

        Kraever confirm=True. Uden det returneres kun et resume af hvad der
        ville blive bestilt.
        """
        summary = self.basket_summary()
        if not confirm:
            return {
                "dry_run": True,
                "message": (
                    "Ingen ordre sendt. Kald igen med confirm=True "
                    "(CLI: --yes) for at bestille."
                ),
                "would_order": summary,
            }
        if summary.get("has_soldout"):
            raise BilkaError(
                "Kurven indeholder udsolgte varer. Ryd dem foerst."
            )
        total = summary.get("total_kr")
        if not total:
            raise BilkaError("Kurven er tom.")

        amount_ore = int(round(total * 100))
        goto = self._request(
            "shop/v3", "GotoPayment", method="POST",
            data={"sum": amount_ore, "amount": amount_ore},
        )
        result = self._request(
            "shop/v3", "CheckOut", method="POST",
            data={"paymentMethod": 8, "amount": amount_ore},
        )
        return {"dry_run": False, "goto_payment": goto, "checkout": result,
                "ordered": summary}


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def _client(args) -> BilkaClient:
    return BilkaClient(username=args.username, password=args.password)


def _emit(args, data: Any, text: str | None = None) -> None:
    if args.json or text is None:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(text)


def cmd_search(args) -> int:
    c = _client(args)
    products = c.search(
        args.query, limit=args.limit, sort=args.sort,
        only_offers=args.offers, in_stock_only=args.in_stock,
    )
    if args.json:
        print(json.dumps([p.to_dict() for p in products],
                         ensure_ascii=False, indent=2))
    elif not products:
        print(f"Ingen varer fundet for '{args.query}'.")
    else:
        print(f"{len(products)} varer for '{args.query}':\n")
        for p in products:
            print(p.line())
    return 0


def cmd_details(args) -> int:
    c = _client(args)
    p = c.get_product(args.product_id)
    if not p:
        print(f"Fandt ikke vare {args.product_id}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(p.raw, ensure_ascii=False, indent=2))
    else:
        d = p.to_dict()
        for key, value in d.items():
            print(f"{key:22} {value}")
    return 0


def cmd_basket(args) -> int:
    c = _client(args)
    basket = c.get_basket()          # ét kald, to visninger
    lines = c._parse_lines(basket)
    summary = c._parse_summary(basket)
    if args.json:
        print(json.dumps(
            {"lines": [{k: v for k, v in line.items() if k != "raw"}
                       for line in lines],
             "summary": summary},
            ensure_ascii=False, indent=2))
        return 0
    if not lines:
        print("Kurven er tom.")
        return 0

    def money(value: Any) -> str:
        return f"{value:.2f}".replace(".", ",") if value is not None else "-"

    for line in lines:
        if line["is_service"]:
            continue
        name = f"{line['name']}"[:50]
        flag = "  [UDSOLGT]" if line["unavailable"] else ""
        print(f"{line['quantity']:>3} x {name:<50} "
              f"{money(line['total_kr']):>9} kr{flag}")
    for fee in summary.get("fees") or []:
        if fee.get("kr"):
            print(f"      {fee['text']:<50} {money(fee['kr']):>9} kr")
    print("-" * 70)
    if summary.get("discount_kr"):
        print(f"{'Rabat':<56} {money(summary['discount_kr']):>9} kr")
    print(f"{'I alt (' + str(summary.get('quantity') or 0) + ' varer)':<56} "
          f"{money(summary.get('total_kr')):>9} kr")
    if summary.get("delivery_message"):
        print(f"Levering: {summary['delivery_message']}")
    if summary.get("has_soldout"):
        print("OBS: kurven indeholder udsolgte varer.")
    return 0


def cmd_add(args) -> int:
    c = _client(args)
    c.add(args.product_id, args.quantity)
    p = c.get_product(args.product_id)
    name = p.name if p else args.product_id
    _emit(args, {"id": str(args.product_id), "added": args.quantity, "name": name},
          f"Lagt i kurv: {args.quantity} x {name}")
    return 0


def cmd_remove(args) -> int:
    c = _client(args)
    c.remove(args.product_id, args.quantity)
    _emit(args, {"id": str(args.product_id), "removed": args.quantity or "alle"},
          f"Fjernet fra kurv: {args.product_id}")
    return 0


def cmd_set(args) -> int:
    c = _client(args)
    c.set_quantity(args.product_id, args.quantity)
    _emit(args, {"id": str(args.product_id), "quantity": args.quantity},
          f"Antal sat til {args.quantity} for {args.product_id}")
    return 0


def cmd_empty(args) -> int:
    c = _client(args)
    if not args.yes:
        print("Tilfoej --yes for at tomme kurven.", file=sys.stderr)
        return 1
    c.empty_basket()
    _emit(args, {"emptied": True}, "Kurven er tomt.")
    return 0


def cmd_history(args) -> int:
    c = _client(args)
    data = c.order_history(limit=args.limit)
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


def cmd_order(args) -> int:
    c = _client(args)
    print(json.dumps(c.order_details(args.order_id), ensure_ascii=False, indent=2))
    return 0


def cmd_reorder(args) -> int:
    c = _client(args)
    c.copy_order(args.order_id)
    _emit(args, {"copied": args.order_id},
          f"Ordre {args.order_id} er kopieret ind i kurven.")
    return 0


def cmd_favorites(args) -> int:
    c = _client(args)
    print(json.dumps(c.favorites(), ensure_ascii=False, indent=2))
    return 0


def cmd_delivery(args) -> int:
    c = _client(args)
    print(json.dumps(c.delivery_dates(), ensure_ascii=False, indent=2))
    return 0


def cmd_profile(args) -> int:
    c = _client(args)
    print(json.dumps(c.profile(), ensure_ascii=False, indent=2))
    return 0


def cmd_shop(args) -> int:
    """Sog og laeg den bedste traeffer i kurven for hver vare pa listen."""
    c = _client(args)
    results = []
    for item in args.items:
        name, _, qty = item.partition(":")
        quantity = int(qty) if qty.strip().isdigit() else 1
        matches = c.search(name.strip(), limit=5, in_stock_only=True)
        if not matches:
            results.append({"query": name, "ok": False, "error": "ingen traeffer"})
            print(f"[ ] {name}: ingen varer fundet")
            continue
        best = matches[0]
        if args.dry_run:
            results.append({"query": name, "ok": True, "dry_run": True,
                            "match": best.to_dict(), "quantity": quantity})
            print(f"[~] {name}: ville laegge {quantity} x {best.name} "
                  f"({kr(best.effective_price)} kr)")
            continue
        try:
            c.add(best.id, quantity)
            results.append({"query": name, "ok": True,
                            "match": best.to_dict(), "quantity": quantity})
            print(f"[x] {name}: {quantity} x {best.name} "
                  f"({kr(best.effective_price)} kr)")
        except BilkaError as exc:
            results.append({"query": name, "ok": False, "error": str(exc)})
            print(f"[ ] {name}: {exc}")
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0


def cmd_checkout(args) -> int:
    c = _client(args)
    result = c.checkout(confirm=args.yes)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_login(args) -> int:
    c = _client(args)
    c.login(force=True)
    print("Logget ind.")
    return 0


def cmd_logout(args) -> int:
    _client(args).logout()
    print("Logget ud.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    # Faellesflag skal virke baade foer og efter underkommandoen, sa bade
    # "bilka --json search x" og "bilka search x --json" gaar an. SUPPRESS
    # gor at et flag der ikke er givet paa underkommandoen ikke nulstiller
    # det samme flag givet foer den.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("-u", "--username", default=argparse.SUPPRESS,
                        help="Bilka-login (ellers BILKA_USERNAME)")
    common.add_argument("-p", "--password", default=argparse.SUPPRESS,
                        help="Kodeord (ellers BILKA_PASSWORD)")
    common.add_argument("--json", action="store_true",
                        default=argparse.SUPPRESS, help="Output som JSON")

    p = argparse.ArgumentParser(
        prog="bilka",
        parents=[common],
        description="Handel ind hos Bilka To Go fra kommandolinjen.",
    )
    p.set_defaults(username=None, password=None, json=False)
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("search", help="Sog efter varer", parents=[common])
    s.add_argument("query")
    s.add_argument("-n", "--limit", type=int, default=20)
    s.add_argument("--sort", choices=["relevance", "price", "unit_price"],
                   default="relevance")
    s.add_argument("--offers", action="store_true", help="Kun varer pa tilbud")
    s.add_argument("--in-stock", action="store_true", help="Kun varer pa lager")
    s.set_defaults(func=cmd_search)

    s = sub.add_parser("details", help="Vis detaljer for en vare", parents=[common])
    s.add_argument("product_id")
    s.set_defaults(func=cmd_details)

    s = sub.add_parser("basket", help="Vis kurven", parents=[common])
    s.set_defaults(func=cmd_basket)

    s = sub.add_parser("add", help="Laeg en vare i kurven", parents=[common])
    s.add_argument("product_id")
    s.add_argument("quantity", nargs="?", type=int, default=1)
    s.set_defaults(func=cmd_add)

    s = sub.add_parser("remove", help="Fjern en vare fra kurven", parents=[common])
    s.add_argument("product_id")
    s.add_argument("quantity", nargs="?", type=int, default=None)
    s.set_defaults(func=cmd_remove)

    s = sub.add_parser("set", help="Saet et absolut antal for en vare", parents=[common])
    s.add_argument("product_id")
    s.add_argument("quantity", type=int)
    s.set_defaults(func=cmd_set)

    s = sub.add_parser("empty", help="Tom kurven", parents=[common])
    s.add_argument("--yes", action="store_true")
    s.set_defaults(func=cmd_empty)

    s = sub.add_parser("shop", help="Sog og laeg en hel indkoebsliste i kurven", parents=[common])
    s.add_argument("items", nargs="+", metavar="VARE[:ANTAL]")
    s.add_argument("--dry-run", action="store_true",
                   help="Vis hvad der ville blive lagt i kurven")
    s.set_defaults(func=cmd_shop)

    s = sub.add_parser("history", help="Ordrehistorik", parents=[common])
    s.add_argument("-n", "--limit", type=int, default=10)
    s.set_defaults(func=cmd_history)

    s = sub.add_parser("order", help="Vis en ordre", parents=[common])
    s.add_argument("order_id")
    s.set_defaults(func=cmd_order)

    s = sub.add_parser("reorder", help="Kopier en tidligere ordre ind i kurven", parents=[common])
    s.add_argument("order_id")
    s.set_defaults(func=cmd_reorder)

    s = sub.add_parser("favorites", help="Vis favoritter", parents=[common])
    s.set_defaults(func=cmd_favorites)

    s = sub.add_parser("delivery", help="Ledige leveringstider", parents=[common])
    s.set_defaults(func=cmd_delivery)

    s = sub.add_parser("profile", help="Vis din profil", parents=[common])
    s.set_defaults(func=cmd_profile)

    s = sub.add_parser("checkout", help="Bestil kurven (koster penge)", parents=[common])
    s.add_argument("--yes", action="store_true",
                   help="Bekraeft. Uden denne koeres dry-run.")
    s.set_defaults(func=cmd_checkout)

    s = sub.add_parser("login", help="Log ind og gem session", parents=[common])
    s.set_defaults(func=cmd_login)

    s = sub.add_parser("logout", help="Log ud og slet session", parents=[common])
    s.set_defaults(func=cmd_logout)

    return p


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:]) if argv is None else list(argv)

    # Argparse kan ikke selv finde ud af et flag der er defineret bade paa
    # hovedparseren og paa underkommandoen - underkommandoens default vinder
    # og nulstiller vaerdien. Vi plukker derfor faellesflagene ud af argv
    # foerst, sa de virker uanset hvor de staar.
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("-u", "--username")
    pre.add_argument("-p", "--password")
    pre.add_argument("--json", action="store_true")
    shared, rest = pre.parse_known_args(argv)

    if not rest or rest[0].startswith("-"):
        # Ingen underkommando tilbage - lad hovedparseren give fejlen.
        rest = argv

    args = build_parser().parse_args(rest)
    args.username = shared.username
    args.password = shared.password
    args.json = shared.json

    try:
        return args.func(args)
    except BilkaError as exc:
        print(f"Fejl: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
