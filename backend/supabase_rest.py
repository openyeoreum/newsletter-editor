from __future__ import annotations

import json
from urllib.parse import urlencode

import httpx

from . import config


class SupabaseRestError(RuntimeError):
    def __init__(self, status: int, body: str):
        self.status = status
        self.body = body
        super().__init__(f"Supabase REST error {status}: {body}")


_client: httpx.Client | None = None


def _http() -> httpx.Client:
    global _client
    if _client is None:
        _client = httpx.Client(timeout=25.0, trust_env=False)
    return _client


def _base_url(table: str, params: dict | None = None) -> str:
    url = f"{config.SUPABASE_URL.rstrip('/')}/rest/v1/{table}"
    if params:
        query = urlencode(params, safe="*,.()")
        url = f"{url}?{query}"
    return url


def _headers(prefer: str | None = None) -> dict:
    headers = {
        "apikey": config.SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {config.SUPABASE_SERVICE_ROLE_KEY}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer
    return headers


def request(method: str, table: str, params: dict | None = None, payload=None, prefer: str | None = None):
    body = None if payload is None else json.dumps(payload, ensure_ascii=False)
    try:
        response = _http().request(method, _base_url(table, params), content=body, headers=_headers(prefer))
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise SupabaseRestError(exc.response.status_code, exc.response.text) from exc
    except httpx.RequestError as exc:
        raise RuntimeError(f"Supabase REST request failed: {exc}") from exc
    if not response.content:
        return []
    return response.json()


def select(table: str, columns: str = "*", filters: dict | None = None, order: str | None = None, limit: int | None = None):
    params = {"select": columns}
    if filters:
        params.update(filters)
    if order:
        params["order"] = order
    if limit is not None:
        params["limit"] = str(limit)
    return request("GET", table, params=params)


def insert(table: str, payload, returning: bool = False):
    prefer = "return=representation" if returning else "return=minimal"
    return request("POST", table, payload=payload, prefer=prefer)


def upsert(table: str, payload, on_conflict: str | None = None, returning: bool = False):
    params = {"on_conflict": on_conflict} if on_conflict else None
    prefer = "resolution=merge-duplicates"
    prefer += ",return=representation" if returning else ",return=minimal"
    return request("POST", table, params=params, payload=payload, prefer=prefer)


def update(table: str, payload: dict, filters: dict, returning: bool = False):
    prefer = "return=representation" if returning else "return=minimal"
    return request("PATCH", table, params=filters, payload=payload, prefer=prefer)


def delete(table: str, filters: dict):
    return request("DELETE", table, params=filters, prefer="return=minimal")
