import pandas as pd
import numpy as np
from datetime import datetime
import json
import os
from dotenv import load_dotenv
import openai
import logging
import requests

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Загрузка переменных окружения
load_dotenv()

def calculate_price_sensitivity(row, metric='units'):
    """Расчет чувствительности к цене"""
    if metric == 'units':
        return 1.0  # Базовая чувствительность
    return 1.0  # Базовая чувствительность для выручки

def format_history(price_history, sales_history):
    """
    Преобразует списки истории цен и продаж в читаемый формат.
    
    Args:
        price_history (list): Список цен
        sales_history (list): Список продаж
        
    Returns:
        str: Отформатированная строка истории
    """
    if not price_history or not sales_history or len(price_history) != len(sales_history):
        return "Нет данных"
    history_pairs = [f"Цена {p:.0f} - {s:.0f} шт." for p, s in zip(price_history, sales_history)]
    return ", ".join(history_pairs)

def process_data(data):
    """Обработка данных с округлением и ограничением колонок"""
    df = data.copy()
    
    # Валидация и парсинг данных
    df['Current_Price'] = pd.to_numeric(df['Current_Price'], errors='coerce')
    df['Cost'] = pd.to_numeric(df['Cost'], errors='coerce')
    df['Current_Stock'] = pd.to_numeric(df['Current_Stock'], errors='coerce')
    df['Sales_30d'] = pd.to_numeric(df['Sales_30d'], errors='coerce')
    df['Competitor_Price'] = pd.to_numeric(df['Competitor_Price'], errors='coerce')
    
    # Парсинг истории
    for col in ['Price_History', 'Sales_History']:
        if col in df.columns:
            df[col] = df[col].apply(lambda x: json.loads(x) if isinstance(x, str) else x)
    
    # Расчет метрик с округлением
    df['Sales_Velocity'] = (df['Sales_30d'] / 30).round(2)
    df['Sales_Velocity'] = df['Sales_Velocity'].replace(0, 0.01)
    df['Stock_Runway'] = (df['Current_Stock'] / df['Sales_Velocity']).round(1)
    df['Discount_Margin'] = ((df['Current_Price'] - df['Cost']) / df['Current_Price'] * 100).round(1)
    
    # Исправленный расчет Competitor_Gap
    df['Competitor_Gap'] = ((df['Current_Price'] - df['Competitor_Price']) / df['Competitor_Price'] * 100).round(1)
    df['Competitor_Gap'] = df['Competitor_Gap'].fillna(0)
    
    # Форматирование истории
    df['History'] = df.apply(lambda row: format_history(
        row.get('Price_History', []),
        row.get('Sales_History', [])
    ), axis=1)
    
    # Генерация рекомендаций
    if os.getenv('OPENAI_API_KEY'):
        df['Recommendation'] = df.apply(get_ai_recommendation, axis=1)
    else:
        df['Recommendation'] = df.apply(generate_basic_recommendation, axis=1)
    
    # Возвращаем только нужные колонки
    return df[['Product', 'Current_Price', 'Cost', 'Current_Stock', 'Sales_30d', 'Competitor_Price', 'History', 'Recommendation']]

def get_ai_recommendation(row):
    """Получение структурированных рекомендаций от OpenAI"""
    try:
        api_key = os.getenv('OPENAI_API_KEY')
        prompt = f"""
        Для товара "{row['Product']}":
        - Цена: {row['Current_Price']} | Себестоимость: {row['Cost']}
        - Остатки: {row['Current_Stock']} | Продажи за 30 дней: {row['Sales_30d']}
        - Цена конкурентов: {row.get('Competitor_Price', 'N/A')}
        - История: {row['History']}
        - Скорость продаж: {row.get('Sales_Velocity', 'N/A')} шт/день
        - Время распродажи: {row.get('Stock_Runway', 'N/A')} дней
        - Чувствительность (шт): {row.get('PS_units', 'N/A')}
        - Праздник: {'Да' if row.get('Is_Holiday_Period', False) else 'Нет'}
        
        Предложи акцию в формате:
        Анализ: [1-2 предложения о текущей ситуации]
        Рекомендация: [конкретное действие]
        Эффект: [ожидаемый результат]
        """
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": "gpt-3.5-turbo", "messages": [{"role": "user", "content": prompt}], "max_tokens": 150},
            timeout=10
        )
        response.raise_for_status()
        return response.json()['choices'][0]['message']['content'].strip()
    except Exception as e:
        logger.error(f"Ошибка OpenAI: {str(e)}")
        return generate_basic_recommendation(row)

def generate_basic_recommendation(row):
    """Генерация базовых рекомендаций без OpenAI"""
    analysis = []
    recommendation = []
    effect = []
    
    # Анализ
    if row['Current_Price'] > row.get('Competitor_Price', float('inf')):
        analysis.append("Цена выше конкурентов")
    if row['Current_Stock'] > 50:
        analysis.append("Высокие остатки")
    if row['Sales_30d'] < 30:
        analysis.append("Низкие продажи")
    
    # Рекомендация
    if row['Current_Price'] > row.get('Competitor_Price', float('inf')):
        recommendation.append("Снизить цену на 10%")
    if row['Current_Stock'] > 50:
        recommendation.append("Запустить акцию распродажи")
    if row['Sales_30d'] < 30:
        recommendation.append("Увеличить рекламный бюджет")
    
    # Эффект
    if recommendation:
        effect.append("Рост продаж на 15-20%")
        effect.append("Снижение остатков")
    
    return f"Анализ: {' | '.join(analysis)}\nРекомендация: {' | '.join(recommendation)}\nЭффект: {' | '.join(effect)}"

def format_price(price):
    """
    Форматирование цены
    """
    return f"{price:.2f}" 