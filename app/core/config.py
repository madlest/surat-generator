import locale
from pydantic_settings import BaseSettings, SettingsConfigDict

try:
    locale.setlocale(locale.LC_TIME, 'id_ID.UTF-8')
except locale.Error:
    raise RuntimeError(
        "Locale 'id_ID.UTF-8' belum terinstall di sistem ini. "
        "Jalankan: sudo locale-gen id_ID.UTF-8 && sudo update-locale"
    )
    
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    soffice_path: str = "soffice" 
    temp_dir: str = "temp"


settings = Settings()