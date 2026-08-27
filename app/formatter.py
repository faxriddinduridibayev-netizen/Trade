from __future__ import annotations

from app.market_news_source import MarketNewsItem, translate_to_uzbek
from app.news_source import NewsEvent
from app.price_source import PriceQuote

IMPACT_EMOJI = {
    "High": "🔴",
    "Medium": "🟠",
    "Low": "🟡",
    "Holiday": "⚪️",
}


def format_news(event: NewsEvent) -> str:
    emoji = IMPACT_EMOJI.get(event.impact, "🟡")
    lines = [
        f"{emoji} <b>{event.title}</b> ({event.country})",
    ]
    if event.actual:
        lines.append(f"📊 Natija: <b>{event.actual}</b>")
    if event.forecast:
        lines.append(f"🎯 Prognoz: {event.forecast}")
    if event.previous:
        lines.append(f"⏮ Oldingi: {event.previous}")

    # Qisqa, lo'nda "tahlil" — actual vs forecast solishtirish orqali
    hint = _quick_hint(event)
    if hint:
        lines.append(f"\n💡 {hint}")

    return "\n".join(lines)


def _quick_hint(event: NewsEvent) -> str | None:
    """Actual va forecast'ni solishtirib, juda qisqa xulosa beradi."""
    try:
        actual_val = float(event.actual.replace("%", "").replace("K", "").strip())
        forecast_val = float(event.forecast.replace("%", "").replace("K", "").strip())
    except (ValueError, AttributeError):
        return None

    if actual_val > forecast_val:
        return "Kutilganidan yuqori chiqdi — milliy valyutaga ijobiy ta'sir qilishi mumkin."
    if actual_val < forecast_val:
        return "Kutilganidan past chiqdi — milliy valyutaga salbiy ta'sir qilishi mumkin."
    return "Prognoz bilan bir xil chiqdi — kuchli ta'sir kutilmaydi."


def format_prices(
    quotes: list[PriceQuote],
    previous: dict[str, float] | None = None,
    title: str = "💹 <b>Bozor narxlari</b>",
) -> str:
    previous = previous or {}
    lines = [title]
    for q in quotes:
        if q.price is None:
            lines.append(f"• {q.label}: ⚠️ ma'lumot yo'q")
            continue

        arrow = ""
        prev_price = previous.get(q.symbol)
        if prev_price is not None:
            if q.price > prev_price:
                arrow = " ⬆️"
            elif q.price < prev_price:
                arrow = " ⬇️"
            else:
                arrow = " ➡️"

        lines.append(f"• {q.label}: <b>{q.price:,.2f}</b>{arrow}")

    return "\n".join(lines)


def format_market_news(item: MarketNewsItem) -> str:
    """Investing.com'dan kelgan iqtisodiy/moliyaviy yangilikni o'zbek
    tiliga tarjima qilib, qisqa va lo'nda formatda tayyorlaydi."""
    title_uz = translate_to_uzbek(item.title_en)
    summary_uz = translate_to_uzbek(item.summary_en) if item.summary_en else ""

    lines = [f"{item.category}", f"<b>{title_uz}</b>"]
    if summary_uz:
        lines.append(summary_uz)
    lines.append(f'\n🔗 <a href="{item.link}">To\'liq o\'qish</a>')

    return "\n".join(lines)
