"""
Investing.com'ning rasmiy RSS feedlari orqali umumiy iqtisodiy va moliyaviy
yangiliklarni olib keladi (ForexFactory kalendaridagi raqamli hodisalardan
farqli o'laroq, bu yerda to'liq maqola sarlavha+qisqacha mazmuni bor).

Manba: https://www.investing.com/webmaster-tools/rss
Barchasi bepul, RSS formatida, API key kerak emas.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import feedparser
import httpx
from deep_translator import GoogleTranslator

FEEDS: dict[str, str] = {
    "💱 Forex": "https://www.investing.com/rss/news_1.rss",
    "📊 Iqtisodiyot": "https://www.investing.com/rss/news_14.rss",
    "📈 Iqtisodiy ko'rsatkichlar": "https://www.investing.com/rss/news_95.rss",
    "🪙 Tovar bozori": "https://www.investing.com/rss/news_11.rss",
}

# Har bir feed tekshiruvida shu turdan qancha yangi maqola postlanishi mumkin
# (kanal spam bo'lib ketmasligi uchun)
MAX_NEW_PER_FEED = 4


@dataclass
class MarketNewsItem:
    id: str
    category: str
    title_en: str
    summary_en: str
    link: str
    published: datetime


def _make_id(link: str) -> str:
    return hashlib.sha256(link.encode()).hexdigest()[:16]


async def _fetch_feed(client: httpx.AsyncClient, category: str, url: str) -> list[MarketNewsItem]:
    try:
        resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0 (compatible; NewsBot/1.0)"})
        resp.raise_for_status()
    except Exception:  # noqa: BLE001
        return []

    parsed = feedparser.parse(resp.content)
    items: list[MarketNewsItem] = []
    for entry in parsed.entries:
        link = entry.get("link", "")
        if not link:
            continue

        published = datetime.now(timezone.utc)
        raw_date = entry.get("published") or entry.get("updated")
        if raw_date:
            try:
                published = parsedate_to_datetime(raw_date)
                if published.tzinfo is None:
                    published = published.replace(tzinfo=timezone.utc)
            except (TypeError, ValueError):
                pass

        summary = entry.get("summary", "") or ""
        # HTML teglaridan tozalash (RSS summary ba'zan oddiy HTML bo'ladi)
        summary = summary.split("<")[0].strip()

        items.append(
            MarketNewsItem(
                id=_make_id(link),
                category=category,
                title_en=entry.get("title", "").strip(),
                summary_en=summary[:280],
                link=link,
                published=published,
            )
        )
    return items


async def fetch_market_news(within_minutes: int = 60) -> list[MarketNewsItem]:
    """Barcha feedlardan so'nggi (within_minutes ichida chiqqan) maqolalarni oladi."""
    now = datetime.now(timezone.utc)
    async with httpx.AsyncClient(timeout=20) as client:
        all_items: list[MarketNewsItem] = []
        for category, url in FEEDS.items():
            items = await _fetch_feed(client, category, url)
            recent = [
                it for it in items
                if (now - it.published).total_seconds() / 60 <= within_minutes
            ]
            all_items.extend(recent[:MAX_NEW_PER_FEED])
        return all_items


def translate_to_uzbek(text: str) -> str:
    """Ingliz tilidagi matnni o'zbek tiliga tarjima qiladi.
    Tarjima muvaffaqiyatsiz bo'lsa, asl matnni qaytaradi (bot to'xtab
    qolmasligi uchun)."""
    if not text:
        return text
    try:
        return GoogleTranslator(source="en", target="uz").translate(text)
    except Exception:  # noqa: BLE001
        return text
