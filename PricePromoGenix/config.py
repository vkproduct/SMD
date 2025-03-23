import os
from dotenv import load_dotenv
import logging

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("app.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Загрузка переменных окружения
load_dotenv()

class Config:
    """Класс конфигурации приложения."""
    
    # Flask настройки
    DEBUG = os.getenv('FLASK_ENV') == 'development'
    PORT = int(os.getenv('PORT', 5000))
    
    # Настройки API
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
    OPENAI_MODEL = os.getenv('OPENAI_MODEL', 'gpt-3.5-turbo')
    
    # Проверка конфигурации
    @classmethod
    def validate(cls):
        """Проверка наличия необходимых настроек."""
        if not cls.OPENAI_API_KEY:
            logger.warning("⚠️ API ключ OpenAI не найден. Будут использованы базовые рекомендации.")
        
        return True

 