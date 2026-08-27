from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Telegram
    bot_token: str
    channel_id: str  # masalan: @mening_kanalim yoki -1001234567890

    # Yangilanish intervallari (soniyada)
    price_update_interval: int = 1200      # 20 daqiqa
    news_check_interval: int = 600         # 10 daqiqa

    # Faqat "High" va "Medium" impactli yangiliklarni yuborish
    min_news_impact: str = "Medium"        # Low / Medium / High


settings = Settings()
