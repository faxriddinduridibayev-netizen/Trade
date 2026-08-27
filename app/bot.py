from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from aiogram import Bot
from aiogram.enums import ParseMode
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import settings
from app.formatter import format_market_news, format_news, format_prices
from app.market_news_source import fetch_market_news
from app.news_source import fetch_events, filter_by_min_impact, only_released_recent
from app.price_source import fetch_all_prices

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("forex_news_bot")

STATE_FILE = Path("state.json")


def _load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"posted_news_ids": [], "posted_market_news_ids": [], "last_prices": {}}


def _save_state(state: dict) -> None:
    # oxirgi 500 ta ID'ni saqlaymiz, fayl cheksiz o'smasligi uchun
    state["posted_news_ids"] = state["posted_news_ids"][-500:]
    state["posted_market_news_ids"] = state.setdefault("posted_market_news_ids", [])[-500:]
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False))


async def calendar_news_job(bot: Bot, state: dict) -> None:
    """ForexFactory iqtisodiy kalendaridan muhim hodisalarni (NFP, CPI va h.k.) yuboradi."""
    try:
        events = await fetch_events()
    except Exception as exc:  # noqa: BLE001
        log.warning("Kalendar yangiliklarini olishda xato: %s", exc)
        return

    events = filter_by_min_impact(events, settings.min_news_impact)
    events = only_released_recent(events, within_minutes=settings.news_check_interval // 60 + 5)

    new_events = [e for e in events if e.id not in state["posted_news_ids"]]
    for event in new_events:
        text = format_news(event)
        try:
            await bot.send_message(settings.channel_id, text, parse_mode=ParseMode.HTML)
            state["posted_news_ids"].append(event.id)
            log.info("Kalendar yangiligi yuborildi: %s", event.title)
        except Exception as exc:  # noqa: BLE001
            log.warning("Xabar yuborishda xato: %s", exc)

    if new_events:
        _save_state(state)


async def market_news_job(bot: Bot, state: dict) -> None:
    """Investing.com'dan umumiy iqtisodiy/moliyaviy yangiliklarni (Forex,
    Iqtisodiyot, Iqtisodiy ko'rsatkichlar, Tovar bozori) yuboradi."""
    try:
        items = await fetch_market_news(within_minutes=settings.news_check_interval // 60 + 10)
    except Exception as exc:  # noqa: BLE001
        log.warning("Bozor yangiliklarini olishda xato: %s", exc)
        return

    posted_ids = state.setdefault("posted_market_news_ids", [])
    new_items = [it for it in items if it.id not in posted_ids]

    for item in new_items:
        text = format_market_news(item)
        try:
            await bot.send_message(settings.channel_id, text, parse_mode=ParseMode.HTML)
            posted_ids.append(item.id)
            log.info("Bozor yangiligi yuborildi: %s", item.title_en)
        except Exception as exc:  # noqa: BLE001
            log.warning("Xabar yuborishda xato: %s", exc)

    if new_items:
        _save_state(state)


async def news_job(bot: Bot, state: dict) -> None:
    """Har 10 daqiqada ishga tushadi: kalendar hodisalari + umumiy
    iqtisodiy/moliyaviy yangiliklar — ikkalasi ham shu bitta siklda tekshiriladi."""
    await calendar_news_job(bot, state)
    await market_news_job(bot, state)


async def price_job(bot: Bot, state: dict) -> None:
    """Oltin, Kumush, BTC, USD/UZS — har 20 daqiqada kanalga yuboriladi."""
    quotes = await fetch_all_prices()
    text = format_prices(quotes, previous=state.get("last_prices", {}))

    try:
        await bot.send_message(settings.channel_id, text, parse_mode=ParseMode.HTML)
    except Exception as exc:  # noqa: BLE001
        log.warning("Narx xabarini yuborishda xato: %s", exc)
        return

    state["last_prices"] = {q.symbol: q.price for q in quotes if q.price is not None}
    _save_state(state)


async def main() -> None:
    bot = Bot(token=settings.bot_token)
    state = _load_state()

    scheduler = AsyncIOScheduler()
    scheduler.add_job(news_job, "interval", seconds=settings.news_check_interval, args=[bot, state])
    scheduler.add_job(price_job, "interval", seconds=settings.price_update_interval, args=[bot, state])
    scheduler.start()

    log.info("Bot ishga tushdi. Kanal: %s", settings.channel_id)

    # Ishga tushishi bilan darhol bir marta ishlatib ko'ramiz
    await price_job(bot, state)
    await news_job(bot, state)

    # Doim ishlab tursin
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
