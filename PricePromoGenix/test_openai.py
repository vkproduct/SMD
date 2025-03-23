import os
import requests
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

def test_openai_connection():
    """
    Проверка соединения с OpenAI API.
    """
    api_key = os.getenv('OPENAI_API_KEY')
    
    if not api_key:
        print("❌ Ошибка: API ключ OpenAI не найден в переменных окружения.")
        return False
    
    print(f"✓ API ключ OpenAI найден: {api_key[:5]}...{api_key[-4:]}")
    
    # Тестовый запрос к OpenAI API
    try:
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": "gpt-3.5-turbo",
                "messages": [{"role": "user", "content": "Привет, это тестовый запрос!"}],
                "max_tokens": 50
            },
            timeout=10
        )
        
        response.raise_for_status()
        result = response.json()
        
        if 'choices' in result and len(result['choices']) > 0:
            message = result['choices'][0]['message']['content']
            print(f"✓ Успешный ответ от OpenAI API: {message}")
            return True
        else:
            print(f"❌ Ошибка в ответе API: {result}")
            return False
            
    except Exception as e:
        print(f"❌ Ошибка при обращении к OpenAI API: {str(e)}")
        return False

if __name__ == "__main__":
    print("Тестирование соединения с OpenAI API...")
    success = test_openai_connection()
    
    if success:
        print("\n✅ Тест пройден успешно! OpenAI API работает корректно.")
    else:
        print("\n❌ Тест не пройден. Проверьте API ключ и соединение с интернетом.") 