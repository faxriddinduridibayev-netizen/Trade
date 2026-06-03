"""
TRADING SIGNAL — Backend (FastAPI + WebSocket)
===============================================
Railway Variables:
    BOT_TOKEN        — @BotFather dan
    CHANNEL_ID       — @kanal_nomi
    ADMIN_ID         — Sizning Telegram ID
    TWELVE_DATA_KEY  — twelvedata.com dan
"""

import os
import asyncio
import logging
import random
import time
import requests
from datetime import datetime, timezone
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from bs4 import BeautifulSoup
from telegram import Bot

# ─── SOZLAMALAR ──────────────────────────────────────────────
BOT_TOKEN       = os.environ.get("BOT_TOKEN",       "")
CHANNEL_ID      = os.environ.get("CHANNEL_ID",      "")
ADMIN_ID        = int(os.environ.get("ADMIN_ID",    "0"))
TWELVE_DATA_KEY = os.environ.get("TWELVE_DATA_KEY", "")
PORT            = int(os.environ.get("PORT",         "8000"))

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
log = logging.getLogger(__name__)

# ─── FAQAT ENG MUHIM YANGILIKLAR ────────────────────────────
WATCHED_EVENTS = [
    "Non-Farm Payrolls",
    "FOMC Statement", "Fed Interest Rate Decision", "FOMC",
    "CPI m/m", "Core CPI m/m", "Consumer Price Index",
    "GDP q/q", "Gross Domestic Product",
    "ECB Rate Decision", "ECB Interest Rate Decision",
    "BOE Rate Decision", "BOE Interest Rate Decision",
    "Unemployment Rate",
]

# ─── VALYUTA JUFTLIKLARI ─────────────────────────────────────
CURRENCY_PAIRS = {
    "USD": ["EUR/USD", "GBP/USD", "USD/JPY", "XAU/USD"],
    "EUR": ["EUR/USD", "EUR/GBP", "EUR/JPY"],
    "GBP": ["GBP/USD", "EUR/GBP", "GBP/JPY"],
}

# ─── TWELVE DATA — KUZATILADIGAN JUFTLIKLAR ─────────────────
# 6 juft × har 15 daqiqada = 576 so'rov/kun (800 limitdan past)
WATCH_SYMBOLS = ["EUR/USD", "GBP/USD", "USD/JPY", "XAU/USD", "BTC/USD", "AUD/USD"]

# ─── HOLAT ───────────────────────────────────────────────────
sent_events:      set[str]  = set()
signal_history:   list[dict] = []
connected_clients: list[WebSocket] = []
live_prices:      dict[str, dict]  = {}  # {"EUR/USD": {"price": 1.0842, "change": 0.12}}

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Safari/604.1",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/119.0.0.0 Safari/537.36",
]


# ─── TWELVE DATA: REAL KURSLAR ───────────────────────────────
async def fetch_prices():
    """Har 15 daqiqada Twelve Data dan real kurslarni oladi.
    Bepul limitda har juftlik uchun alohida so'rov yuboriladi.
    6 juftlik × 2 so'rov/soat = 288 so'rov/kun (800 dan past).
    """
    if not TWELVE_DATA_KEY:
        log.warning("TWELVE_DATA_KEY yo'q — kurslar yangilanmaydi")
        return

    updates = {}
    for sym in WATCH_SYMBOLS:
        try:
            url = (
                f"https://api.twelvedata.com/price"
                f"?symbol={sym}&apikey={TWELVE_DATA_KEY}"
            )
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            data = resp.json()

            price_str = data.get("price")
            if price_str:
                new_price = float(price_str)
                old = live_prices.get(sym, {}).get("price", new_price)
                change = round((new_price - old) / old * 100, 4) if old else 0
                live_prices[sym] = {"price": new_price, "change": change}
                updates[sym] = {"price": new_price, "change": change}
                log.info("%s = %s", sym, new_price)
            else:
                log.warning("%s uchun javob: %s", sym, data)

            time.sleep(1)  # Rate limit — so'rovlar orasida 1 soniya

        except Exception as e:
            log.error("Twelve Data xatosi (%s): %s", sym, e)

    if updates:
        await broadcast({"type": "prices", "data": updates})
        log.info("Kurslar yangilandi: %d ta juftlik", len(updates))


# ─── FOREXFACTORY: FAQAT MUHIM YANGILIKLAR ──────────────────
def fetch_forexfactory() -> list[dict]:
    """
    ForexFactory dan faqat yuqori muhimlikdagi (qizil) yangiliklar.
    Bloklanmaslik uchun: tasodifiy User-Agent + pauza.
    """
    url = "https://www.forexfactory.com/calendar"
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Referer": "https://www.google.com/",
    }
    try:
        time.sleep(random.uniform(2, 4))  # bloklanmaslik uchun pauza
        resp = requests.get(url, headers=headers, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        events = []
        current_time = ""

        for row in soup.select("tr.calendar__row"):
            time_cell = row.select_one(".calendar__time")
            if time_cell and time_cell.text.strip():
                current_time = time_cell.text.strip()

            impact = row.select_one(".calendar__impact")
            if not impact:
                continue
            if "red" not in " ".join(impact.get("class", [])):
                continue  # Faqat qizil (yuqori muhimlik)

            currency   = row.select_one(".calendar__currency")
            event_cell = row.select_one(".calendar__event-title")
            actual     = row.select_one(".calendar__actual")
            forecast   = row.select_one(".calendar__forecast")
            previous   = row.select_one(".calendar__previous")

            title = event_cell.text.strip() if event_cell else ""

            # Faqat kuzatiladigan yangiliklar
            if not any(w.lower() in title.lower() for w in WATCHED_EVENTS):
                continue

            events.append({
                "time":     current_time,
                "currency": currency.text.strip()   if currency   else "",
                "title":    title,
                "actual":   actual.text.strip()     if actual     else "",
                "forecast": forecast.text.strip()   if forecast   else "",
                "previous": previous.text.strip()   if previous   else "",
            })

        log.info("ForexFactory: %d muhim yangilik topildi", len(events))
        return events

    except Exception as e:
        log.error("ForexFactory xatosi: %s", e)
        return []


# ─── TAHLIL ──────────────────────────────────────────────────
def analyze(event: dict) -> dict:
    def to_num(s: str):
        s = s.replace("%","").replace("K","000").replace("M","000000")
        s = s.replace(",","").strip()
        try:
            return float(s)
        except ValueError:
            return None

    act = to_num(event["actual"])
    fct = to_num(event["forecast"])
    prv = to_num(event["previous"])
    signal, prob, note = "NEUTRAL", 50, "Ma'lumot yetarli emas"

    if act is not None:
        if fct is not None and prv is not None:
            vf = act - fct
            vp = act - prv
            if vf > 0 and vp > 0:
                signal, prob = "BUY",  min(85, 60 + abs(vf / (abs(fct) + 0.001)) * 100)
                note = f"Kutilgandan +{abs(vf):.1f} yuqori, o'tgandan ham yuqori"
            elif vf < 0 and vp < 0:
                signal, prob = "SELL", min(85, 60 + abs(vf / (abs(fct) + 0.001)) * 100)
                note = f"Kutilgandan {abs(vf):.1f} past, o'tgandan ham past"
            elif vf > 0:
                signal, prob, note = "BUY",  58, "Kutilgandan yuqori, o'tgandan past"
            elif vf < 0:
                signal, prob, note = "SELL", 58, "Kutilgandan past, o'tgandan yuqori"
        elif fct is not None:
            if act > fct:   signal, prob, note = "BUY",  62, "Kutilgandan yuqori"
            elif act < fct: signal, prob, note = "SELL", 62, "Kutilgandan past"
        elif prv is not None:
            if act > prv:   signal, prob, note = "BUY",  55, "O'tgan davrdan yuqori"
            elif act < prv: signal, prob, note = "SELL", 55, "O'tgan davrdan past"

    return {
        "signal":      signal,
        "probability": round(prob),
        "note":        note,
        "pairs":       CURRENCY_PAIRS.get(event["currency"], [f"{event['currency']}/USD"]),
    }


# ─── TELEGRAM ────────────────────────────────────────────────
def format_telegram(event: dict, res: dict) -> str:
    sig  = res["signal"]
    icon = "🟢" if sig == "BUY" else ("🔴" if sig == "SELL" else "⚪")
    pairs = " | ".join(res["pairs"][:3])
    return (
        f"📊 <b>{event['title']}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🔵 Haqiqiy:  <b>{event['actual'] or '—'}</b>\n"
        f"⬜ Kutilgan: {event['forecast'] or '—'}\n"
        f"🔘 Oldingi:  {event['previous'] or '—'}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📌 <i>{res['note']}</i>\n\n"
        f"{icon} <b>{sig}</b> {event['currency']} — ehtimoli: <b>{res['probability']}%</b>\n"
        f"💱 {pairs}\n"
        f"⏰ {event['time']} UTC"
    )


# ─── WEBSOCKET BROADCAST ─────────────────────────────────────
async def broadcast(data: dict):
    dead = []
    for ws in connected_clients:
        try:
            await ws.send_json(data)
        except Exception:
            dead.append(ws)
    for ws in dead:
        if ws in connected_clients:
            connected_clients.remove(ws)


# ─── YANGILIK TEKSHIRISH ─────────────────────────────────────
async def check_news():
    events = fetch_forexfactory()
    for event in events:
        if not event["actual"]:
            continue
        key = f"{event['time']}_{event['title']}"
        if key in sent_events:
            continue

        res = analyze(event)
        now = datetime.now(timezone.utc).strftime("%H:%M:%S")

        payload = {
            "type":        "signal",
            "time":        now,
            "title":       event["title"],
            "currency":    event["currency"],
            "actual":      event["actual"],
            "forecast":    event["forecast"],
            "previous":    event["previous"],
            "signal":      res["signal"],
            "probability": res["probability"],
            "note":        res["note"],
            "pairs":       res["pairs"],
        }

        signal_history.insert(0, payload)
        if len(signal_history) > 50:
            signal_history.pop()

        await broadcast(payload)

        if BOT_TOKEN:
            bot = Bot(token=BOT_TOKEN)
            msg = format_telegram(event, res)
            if CHANNEL_ID:
                try:
                    await bot.send_message(CHANNEL_ID, msg, parse_mode="HTML")
                except Exception as e:
                    log.error("Kanal xato: %s", e)
            if ADMIN_ID:
                try:
                    await bot.send_message(ADMIN_ID, msg, parse_mode="HTML")
                except Exception as e:
                    log.error("Admin xato: %s", e)

        sent_events.add(key)
        log.info("Signal: %s | %s %s%%", event["title"], res["signal"], res["probability"])


# ─── TELEGRAM BOT KOMANDALAR ────────────────────────────────
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram import Update

tg_app: Application | None = None

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📊 <b>Trading Signal Panel</b>\n\n"
        "Muhim iqtisodiy yangiliklar kelganda signal yuboraman.\n\n"
        "/status — Bot holati\n"
        "/test   — Test signal yuborish\n"
        "/today  — Bugungi muhim yangiliklar",
        parse_mode="HTML",
    )

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now(timezone.utc)
    await update.message.reply_text(
        f"✅ Bot ishlayapti\n"
        f"🕐 UTC: {now.strftime('%H:%M:%S')}\n"
        f"📨 Yuborilgan signallar: {len(signal_history)} ta\n"
        f"💱 Kurslar: {len(live_prices)} ta juftlik\n"
        f"🔄 Kurs yangilanish: har 15 daqiqada\n"
        f"📰 Yangilik tekshirish: har 30 daqiqada",
    )

async def cmd_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    test_event = {
        "time": "15:30",
        "currency": "USD",
        "title": "Non-Farm Payrolls",
        "actual": "220K",
        "forecast": "180K",
        "previous": "200K",
    }
    res = analyze(test_event)
    now = datetime.now(timezone.utc).strftime("%H:%M:%S")
    payload = {
        "type":        "signal",
        "time":        now,
        "title":       test_event["title"],
        "currency":    test_event["currency"],
        "actual":      test_event["actual"],
        "forecast":    test_event["forecast"],
        "previous":    test_event["previous"],
        "signal":      res["signal"],
        "probability": res["probability"],
        "note":        res["note"],
        "pairs":       res["pairs"],
    }
    signal_history.insert(0, payload)
    await broadcast(payload)
    msg = format_telegram(test_event, res)
    await update.message.reply_text("📋 Test signal:\n\n" + msg, parse_mode="HTML")

async def cmd_today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "⏳ ForexFactory tekshirilmoqda...",
    )
    events = fetch_forexfactory()
    if not events:
        await update.message.reply_text(
            "📭 Bugun yuqori muhimlikdagi yangilik topilmadi.\n"
            "Muhim yangiliklar: Payshanba (ECB), Juma (NFP) da kutilmoqda."
        )
        return
    lines = ["📅 <b>Bugungi muhim yangiliklar:</b>\n"]
    for e in events[:10]:
        actual = f" → <b>{e['actual']}</b>" if e["actual"] else ""
        lines.append(f"⏰ {e['time']} | {e['currency']} | {e['title']}{actual}")
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")

async def start_bot_polling():
    """Telegram bot ni background da ishga tushirish."""
    global tg_app
    if not BOT_TOKEN:
        log.warning("BOT_TOKEN yo'q — Telegram bot ishlamaydi")
        return
    tg_app = Application.builder().token(BOT_TOKEN).build()
    tg_app.add_handler(CommandHandler("start",  cmd_start))
    tg_app.add_handler(CommandHandler("status", cmd_status))
    tg_app.add_handler(CommandHandler("test",   cmd_test))
    tg_app.add_handler(CommandHandler("today",  cmd_today))
    await tg_app.initialize()
    await tg_app.start()
    await tg_app.updater.start_polling(drop_pending_updates=True)
    log.info("Telegram bot polling boshlandi!")

async def stop_bot_polling():
    global tg_app
    if tg_app:
        await tg_app.updater.stop()
        await tg_app.stop()
        await tg_app.shutdown()

# ─── FASTAPI ─────────────────────────────────────────────────
scheduler = AsyncIOScheduler(timezone="UTC")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Kurslar: har 15 daqiqada
    scheduler.add_job(fetch_prices, "interval", minutes=15, id="prices")
    # Yangiliklar: har 30 daqiqada
    scheduler.add_job(check_news,  "interval", minutes=30, id="news")
    scheduler.start()
    # Ishga tushganda darhol kurslarni olish
    await fetch_prices()
    # Telegram bot polling ni ishga tushirish
    await start_bot_polling()
    log.info("Server ishga tushdi!")
    yield
    await stop_bot_polling()
    scheduler.shutdown()

app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/", response_class=HTMLResponse)
async def root():
    with open("index.html", encoding="utf-8") as f:
        return f.read()

@app.get("/api/signals")
async def get_signals():
    return {"signals": signal_history}

@app.get("/api/prices")
async def get_prices():
    return {"prices": live_prices}

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    connected_clients.append(ws)
    log.info("WebSocket ulandi. Jami: %d", len(connected_clients))

    # Ulanganida darhol joriy ma'lumotlarni yuborish
    if live_prices:
        await ws.send_json({"type": "prices", "data": live_prices})
    for sig in signal_history[:10]:
        await ws.send_json(sig)

    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        if ws in connected_clients:
            connected_clients.remove(ws)
        log.info("WebSocket uzildi. Qolgan: %d", len(connected_clients))
