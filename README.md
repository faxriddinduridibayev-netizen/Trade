# Forex News Bot (O'zbek tilida)

ForexFactory kalendaridan muhim iqtisodiy hodisalarni, Investing.com'dan
umumiy iqtisodiy/moliyaviy yangiliklarni (avtomatik o'zbek tiliga tarjima
qilingan holda) va Oltin/Kumush/USD-UZS/BTC narxlarini avtomatik ravishda
Telegram kanaliga yuboradigan bot.

## Ishga tushirish

```bash
python -m venv venv
source venv/bin/activate  # Windowsda: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# .env faylini to'ldiring: BOT_TOKEN, CHANNEL_ID

python main.py
```

Bot ishga tushishidan oldin:
1. @BotFather orqali bot yarating va tokenni oling
2. Botni kanalingizga **admin** qilib qo'shing (xabar yuborish huquqi bilan)
3. Boshqa hech qanday ro'yxatdan o'tish yoki API key kerak emas — barcha
   4 ta narx manbasi (Oltin, Kumush, BTC, USD/UZS) to'liq bepul va kalitsiz

## Railway'ga deploy qilish

1. Ushbu papkani GitHub repo qiling
2. Railway'da "New Project" → "Deploy from GitHub repo"
3. Railway avtomatik `Procfile`ni topib, `worker` processini ishga tushiradi
4. Railway loyihasining "Variables" bo'limiga `.env.example`dagi barcha
   o'zgaruvchilarni qo'shing

## Fayl tuzilishi

```
app/
  config.py           # sozlamalar (.env dan o'qiydi)
  news_source.py       # ForexFactory JSON kalendar feedi
  market_news_source.py # Investing.com RSS (Forex/Iqtisodiyot/...) + tarjima
  price_source.py      # gold-api.com + Binance + cbu.uz narxlar
  formatter.py           # Telegram uchun O'zbek tilidagi matn formatlash
  bot.py                 # asosiy scheduler + botning ishga tushishi
main.py
```

## Ma'lumot manbalari (barchasi bepul, kalitsiz)

| Aktiv | Manba | Cheklov |
|---|---|---|
| Oltin (XAU), Kumush (XAG) | [gold-api.com](https://gold-api.com) | Cheklovsiz (30s keshlash tavsiya etiladi) |
| BTC | Binance public API | Amalda cheklovsiz |
| USD/UZS | [cbu.uz](https://cbu.uz) — O'zbekiston Markaziy banki rasmiy API'si | Kunlik yangilanadi |
| Kalendar hodisalari (NFP, CPI va h.k.) | ForexFactory JSON kalendar feedi | — |
| Forex / Iqtisodiyot / Iqtisodiy ko'rsatkichlar / Tovar bozori yangiliklari | [Investing.com RSS](https://www.investing.com/webmaster-tools/rss) | — |

Investing.com'dan kelgan maqolalar ingliz tilida bo'lgani uchun `deep-translator`
kutubxonasi (Google Translate, bepul, kalitsiz) orqali sarlavha va qisqacha
mazmun avtomatik o'zbek tiliga o'giriladi.

## Muhim eslatmalar

- **Yangiliklar** (kalendar hodisalari + Investing.com maqolalari) standart
  holatda **har 10 daqiqada** tekshiriladi (`NEWS_CHECK_INTERVAL=600`).
- **Narxlar posti** standart holatda **har 20 daqiqada** kanalga yuboriladi
  (`PRICE_UPDATE_INTERVAL=1200`). Bu barcha 4 ta manba uchun cheklovsiz
  bo'lgani sababli xohlagancha tezlashtirish yoki sekinlashtirish mumkin.
- **USD/UZS** rasmiy CBU kursi bo'lgani uchun kuniga bir marta yangilanadi
  — shuning uchun ketma-ket bir necha postda bir xil qiymat chiqishi
  normal holat, bu xato emas.
- **ForexFactory feed**: `nfs.faireconomy.media` — bu rasmiy bo'lmagan,
  lekin ko'plab trading botlar tomonidan ishlatiladigan barqaror manba.
  Agar u ishlamay qolsa, `app/news_source.py` faylida shunga o'xshash
  interfeys bilan boshqa manbaga almashtirish mumkin.
- **Investing.com RSS tarjimasi**: `deep-translator` Google Translate'ning
  norasmiy (bepul) endpointidan foydalanadi — juda ko'p so'rov yuborilsa
  vaqtincha bloklanishi mumkin. Shuning uchun har bir feed'dan bir siklda
  faqat so'nggi ~4 ta yangi maqola tarjima qilinadi
  (`app/market_news_source.py` dagi `MAX_NEW_PER_FEED`).
- **Narx o'zgarish belgilari** (⬆️⬇️➡️) oldingi yuborilgan narx bilan
  solishtirib chiqariladi, `state.json` faylida saqlanadi.
- Xabarlar spam bo'lib ketmasligi uchun kalendar hodisalari faqat "Medium"
  va undan yuqori impact darajasida, va faqat natija (`actual`) e'lon
  qilingandan keyin yuboriladi; har ikkala yangilik turi ham `state.json`da
  saqlangan ID'lar orqali dublikatsiz yuboriladi.

## Kengaytirish g'oyalari

- `/narxlar` va `/bugungi_yangiliklar` kabi buyruqlar qo'shish (on-demand)
- Claude/GPT orqali yangilikni yanada "jonli" tahlil bilan boyitish
- Obuna tizimi (Click/Payme) bilan premium kanal — signal ilovangizga
  o'xshab
