#!/usr/bin/env python3
"""MCP-server for Bilka To Go.

Eksponerer bilka_cli som MCP-tools, sa en assistent kan sooge varer, styre
kurven og bestille.

Nye endpoints hoerer hjemme i bilka_cli.py - denne fil pakker dem kun ind.

Koersel:
    uv run server.py
"""

from __future__ import annotations

import os
from typing import Any

from fastmcp import FastMCP

from bilka_cli import BilkaClient, BilkaError, ore_to_kr

mcp = FastMCP("bilka-to-go")

_client: BilkaClient | None = None


def client() -> BilkaClient:
    global _client
    if _client is None:
        _client = BilkaClient()
    return _client


def _safe(fn, *args, **kwargs) -> Any:
    """Kald klienten og oversaet fejl til noget en model kan handle pa."""
    try:
        return fn(*args, **kwargs)
    except BilkaError as exc:
        return {"error": str(exc)}


# ---------------------------------------------------------------- soegning

@mcp.tool
def search_products(
    query: str,
    limit: int = 10,
    only_offers: bool = False,
    in_stock_only: bool = True,
    sort: str = "relevance",
) -> list[dict]:
    """Sog efter varer hos Bilka To Go.

    sort: "relevance", "price" (billigst foerst) eller "unit_price"
    (billigst pr. kilo/liter). Kraever ikke login.
    """
    products = _safe(
        client().search, query, limit=limit, only_offers=only_offers,
        in_stock_only=in_stock_only, sort=sort,
    )
    if isinstance(products, dict):
        return [products]
    return [p.to_dict() for p in products]


@mcp.tool
def get_product(product_id: str) -> dict:
    """Hent alle detaljer om en enkelt vare ud fra dens id."""
    p = _safe(client().get_product, product_id)
    if isinstance(p, dict):
        return p
    return p.to_dict() if p else {"error": f"Fandt ikke vare {product_id}"}


# -------------------------------------------------------------------- kurv

@mcp.tool
def get_basket() -> dict:
    """Vis hvad der ligger i kurven lige nu, med total."""
    lines = _safe(client().basket_lines)
    if isinstance(lines, dict):
        return lines
    summary = _safe(client().basket_summary)
    return {
        "lines": [
            {k: v for k, v in line.items() if k != "raw"} for line in lines
        ],
        "summary": summary,
    }


@mcp.tool
def add_to_basket(product_id: str, quantity: int = 1) -> dict:
    """Laeg en vare i kurven. Brug search_products foerst for at finde id'et."""
    result = _safe(client().add, product_id, quantity)
    if isinstance(result, dict) and result.get("error"):
        return result
    return {"ok": True, "product_id": product_id, "added": quantity}


@mcp.tool
def remove_from_basket(product_id: str, quantity: int | None = None) -> dict:
    """Fjern en vare fra kurven. Uden quantity fjernes hele linjen."""
    result = _safe(client().remove, product_id, quantity)
    if isinstance(result, dict) and result.get("error"):
        return result
    return {"ok": True, "product_id": product_id, "removed": quantity or "alle"}


@mcp.tool
def set_basket_quantity(product_id: str, quantity: int) -> dict:
    """Saet et praecist antal af en vare i kurven."""
    result = _safe(client().set_quantity, product_id, quantity)
    if isinstance(result, dict) and result.get("error"):
        return result
    return {"ok": True, "product_id": product_id, "quantity": quantity}


@mcp.tool
def add_shopping_list(items: list[dict]) -> list[dict]:
    """Laeg en hel indkoebsliste i kurven.

    items er en liste af {"query": "letmaelk", "quantity": 2}. For hver
    linje soeges der, og den bedste traeffer paa lager laegges i kurven.
    Returnerer hvad der blev valgt, sa det kan gennemgaas bagefter.
    """
    c = client()
    results = []
    for item in items:
        query = str(item.get("query", "")).strip()
        quantity = int(item.get("quantity", 1) or 1)
        if not query:
            continue
        matches = _safe(c.search, query, limit=5, in_stock_only=True)
        if isinstance(matches, dict):
            results.append({"query": query, "ok": False,
                            "error": matches["error"]})
            continue
        if not matches:
            results.append({"query": query, "ok": False,
                            "error": "ingen varer fundet"})
            continue
        best = matches[0]
        outcome = _safe(c.add, best.id, quantity)
        if isinstance(outcome, dict) and outcome.get("error"):
            results.append({"query": query, "ok": False,
                            "error": outcome["error"]})
            continue
        results.append({
            "query": query, "ok": True, "quantity": quantity,
            "chosen": best.to_dict(),
            "alternatives": [m.to_dict() for m in matches[1:4]],
        })
    return results


@mcp.tool
def empty_basket() -> dict:
    """Tom hele kurven."""
    result = _safe(client().empty_basket)
    if isinstance(result, dict) and result.get("error"):
        return result
    return {"ok": True, "emptied": True}


@mcp.tool
def add_voucher(code: str) -> dict:
    """Indloes en rabatkode paa kurven."""
    return _safe(client().add_voucher, code)


# ------------------------------------------------------------------ ordrer

@mcp.tool
def order_history(limit: int = 10) -> dict:
    """Vis tidligere ordrer."""
    return _safe(client().order_history, limit)


@mcp.tool
def order_details(order_id: str) -> dict:
    """Vis en enkelt ordre med alle linjer."""
    return _safe(client().order_details, order_id)


@mcp.tool
def reorder(order_id: str) -> dict:
    """Kopier en tidligere ordre ind i kurven - 'det samme som sidst'."""
    result = _safe(client().copy_order, order_id)
    if isinstance(result, dict) and result.get("error"):
        return result
    return {"ok": True, "copied_order": order_id}


@mcp.tool
def favorites() -> dict:
    """Vis dine gemte favoritvarer."""
    return _safe(client().favorites)


# ---------------------------------------------------------------- levering

@mcp.tool
def delivery_dates() -> dict:
    """Vis ledige leveringstider."""
    return _safe(client().delivery_dates)


@mcp.tool
def set_delivery_date(date: str, interval_start: str, interval_end: str) -> dict:
    """Vaelg leveringstid. Brug delivery_dates for gyldige vaerdier."""
    return _safe(client().set_delivery_date, date, interval_start, interval_end)


@mcp.tool
def profile() -> dict:
    """Vis kontooplysninger og leveringsadresse."""
    return _safe(client().profile)


# ---------------------------------------------------------------- checkout

@mcp.tool
def checkout(confirm: bool = False) -> dict:
    """Bestil kurven. Dette koster rigtige penge.

    Uden confirm=True koeres kun en tor visning af hvad der ville blive
    bestilt. Spoerg altid brugeren udtrykkeligt, og vis totalen, foer du
    kalder med confirm=True.
    """
    if confirm and not _truthy(os.environ.get("BILKA_ALLOW_CHECKOUT", "")):
        return {
            "error": (
                "Bestilling er slaaet fra. Saet BILKA_ALLOW_CHECKOUT=1 i "
                "miljoeet for at tillade at denne server sender ordrer."
            ),
            "would_order": _safe(client().basket_summary),
        }
    return _safe(client().checkout, confirm)


def _truthy(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y", "ja"}


if __name__ == "__main__":
    mcp.run()
