"""
ForexFactory'ning rasmiy bo'lmagan, lekin keng ishlatiladigan JSON kalendar
feed'idan foydalanamiz: nfs.faireconomy.media (ForexFactory shu manbadan
kalendar ma'lumotlarini oladi). Bu to'g'ridan-to'g'ri HTML scraping'dan
ko'ra ancha barqaror, chunki Cloudflare himoyasiga duch kelmaydi.

Muhim eslatma: agar bu feed keyinchalik yopilib qolsa, fallback sifatida
Investing.com yoki TradingEconomics RSS'ga o'tish kerak bo'ladi
(alohida adapter yozib, NewsSource interfeysini bajarish kifoya).
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import httpx

FF_WEEKLY_JSON_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"

IMPACT_ORDER = {"Low": 1, "Medium": 2, "High": 3, "Holiday": 0}


@dataclass
class NewsEvent:
    id: str
    title: str
    country: str
    impact: str
    date: datetime
    forecast: str
    previous: str
    actual: str

    @property
    def is_released(self) -> bool:
        return bool(self.actual)


def _make_id(raw: dict) -> str:
    key = f"{raw.get('title')}|{raw.get('country')}|{raw.get('date')}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


async def fetch_events() -> list[NewsEvent]:
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(
            FF_WEEKLY_JSON_URL,
            headers={"User-Agent": "Mozilla/5.0 (compatible; NewsBot/1.0)"},
        )
        resp.raise_for_status()
        raw_events = resp.json()

    events: list[NewsEvent] = []
    for raw in raw_events:
        try:
            dt = datetime.fromisoformat(raw["date"].replace("Z", "+00:00"))
        except (KeyError, ValueError):
            continue

        events.append(
            NewsEvent(
                id=_make_id(raw),
                title=raw.get("title", "").strip(),
                country=raw.get("country", "").strip(),
                impact=raw.get("impact", "Low").strip(),
                date=dt,
                forecast=str(raw.get("forecast", "") or ""),
                previous=str(raw.get("previous", "") or ""),
                actual=str(raw.get("actual", "") or ""),
            )
        )
    return events


def filter_by_min_impact(events: list[NewsEvent], min_impact: str) -> list[NewsEvent]:
    threshold = IMPACT_ORDER.get(min_impact, 2)
    return [e for e in events if IMPACT_ORDER.get(e.impact, 0) >= threshold]


def only_released_recent(
    events: list[NewsEvent], within_minutes: int = 30
) -> list[NewsEvent]:
    """Faqat yaqinda 'actual' natijasi chiqqan hodisalarni qaytaradi —
    bot shu daqiqada bozorga ta'sir qilayotgan narsalarni ushlab qoladi."""
    now = datetime.now(timezone.utc)
    result = []
    for e in events:
        if not e.is_released:
            continue
        delta_min = abs((now - e.date).total_seconds()) / 60
        if delta_min <= within_minutes:
            result.append(e)
    return result
