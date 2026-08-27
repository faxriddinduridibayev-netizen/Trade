from __future__ import annotations

from dataclasses import dataclass

import httpx

GOLD_API_BASE = "https://api.gold-api.com"
CBU_URL = "https://cbu.uz/uz/arkhiv-kursov-valyut/json/all/"
BINANCE_URL = "https://api.binance.com/api/v3/ticker/price"


@dataclass
class PriceQuote:
    symbol: str
    label: str
    price: float | None
    error: str | None = None


# ---------------------------------------------------------------------------
# 4 ta aktiv — barchasi API key kerak bo'lmagan, cheklovsiz bepul manbalar:
#   - Oltin, Kumush → gold-api.com   (manba: https://gold-api.com/llms.txt)
#   - BTC           → Binance public API
#   - USD/UZS       → O'zbekiston Markaziy banki rasmiy API'si (cbu.uz)
# ---------------------------------------------------------------------------
GOLD_API_SYMBOLS = {
    "XAU": "Oltin (XAU/USD)",
    "XAG": "Kumush (XAG/USD)",
}


async def _fetch_gold_api_price(client: httpx.AsyncClient, symbol: str) -> PriceQuote:
    label = GOLD_API_SYMBOLS[symbol]
    try:
        resp = await client.get(f"{GOLD_API_BASE}/price/{symbol}")
        data = resp.json()
        return PriceQuote(symbol=symbol, label=label, price=float(data["price"]))
    except Exception as exc:  # noqa: BLE001
        return PriceQuote(symbol=symbol, label=label, price=None, error=str(exc))


async def _fetch_btc_price(client: httpx.AsyncClient) -> PriceQuote:
    try:
        resp = await client.get(BINANCE_URL, params={"symbol": "BTCUSDT"})
        data = resp.json()
        return PriceQuote(symbol="BTC/USD", label="Bitcoin (BTC/USD)", price=float(data["price"]))
    except Exception as exc:  # noqa: BLE001
        return PriceQuote(symbol="BTC/USD", label="Bitcoin (BTC/USD)", price=None, error=str(exc))


async def _fetch_usd_uzs_price(client: httpx.AsyncClient) -> PriceQuote:
    """O'zbekiston Markaziy banki rasmiy USD/UZS kursi (kalitsiz, bepul).
    Eslatma: bu rasmiy kurs kuniga bir marta yangilanadi, shuning uchun
    ketma-ket postlarda ba'zan bir xil qiymat chiqishi normal holat."""
    label = "Dollar / So'm (USD/UZS, rasmiy CBU kursi)"
    try:
        resp = await client.get(CBU_URL)
        data = resp.json()
        usd_entry = next((item for item in data if item.get("Ccy") == "USD"), None)
        if not usd_entry:
            return PriceQuote(symbol="USD/UZS", label=label, price=None, error="USD topilmadi")
        rate = float(usd_entry["Rate"].replace(",", "."))
        return PriceQuote(symbol="USD/UZS", label=label, price=rate)
    except Exception as exc:  # noqa: BLE001
        return PriceQuote(symbol="USD/UZS", label=label, price=None, error=str(exc))


async def fetch_all_prices() -> list[PriceQuote]:
    """4 ta aktivni birga olib keladi: Oltin, Kumush, BTC, USD/UZS."""
    async with httpx.AsyncClient(timeout=15) as client:
        results = [await _fetch_gold_api_price(client, s) for s in GOLD_API_SYMBOLS]
        results.append(await _fetch_btc_price(client))
        results.append(await _fetch_usd_uzs_price(client))
        return results
