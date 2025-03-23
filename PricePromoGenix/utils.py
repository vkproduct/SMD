import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import holidays
import json
import logging
import requests
import os
import ast

logger = logging.getLogger(__name__)

def process_data(data):
    """
    Обработка данных с расчетом всех метрик и генерацией рекомендаций.
    
    Args:
        data: DataFrame с исходными данными
        
    Returns:
        DataFrame с рассчитанными метриками и рекомендациями
    """
    try:
        df = data.copy()
        
        # Проверка обязательных колонок
        required_cols = ['Product', 'Current_Price', 'Cost', 'Current_Stock', 'Sales_30d']
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            raise ValueError(f"Отсутствуют обязательные колонки: {', '.join(missing_cols)}")
        
        # Обработка истории цен и продаж
        df['Price_History'] = df.get('Price_History', pd.Series([None] * len(df))).apply(parse_history)
        df['Price_History'] = df.apply(lambda row: row['Price_History'] if row['Price_History'] else [row['Current_Price']], axis=1)
        
        df['Sales_History'] = df.get('Sales_History', pd.Series([None] * len(df))).apply(parse_history)
        df['Sales_History'] = df.apply(lambda row: row['Sales_History'] if row['Sales_History'] else [row['Sales_30d']], axis=1)
        
        # Расчет базовых метрик
        df['Sales_Velocity'] = df['Sales_30d'] / 30
        df['Sales_Velocity'] = df['Sales_Velocity'].replace(0, 0.01)  # Избегаем деления на ноль
        
        df['Stock_Runway'] = df['Current_Stock'] / df['Sales_Velocity']
        df['Discount_Margin'] = (df['Current_Price'] - df['Cost']) / df['Current_Price'] * 100
        
        # Сравнение с конкурентами
        df['Competitor_Gap'] = df.get('Competitor_Price', pd.Series([None] * len(df))).apply(
            lambda x: (df['Current_Price'] - x) / x * 100 if pd.notna(x) and x > 0 else 0
        )
        
        # Чувствительность к цене
        df['PS_units'] = df.apply(lambda row: calculate_price_sensitivity(row, 'units'), axis=1)
        df['PS_revenue'] = df.apply(lambda row: calculate_price_sensitivity(row, 'revenue'), axis=1)
        
        # Сезонный фактор
        df['Seasonal_Demand_Factor'] = df.get('Past_Period_Sales', df['Sales_30d']).apply(
            lambda x: df['Sales_30d'] / x if pd.notna(x) and x > 0 else 1
        )
        
        # Проверка праздников (по каждой строке)
        current_date = "2025-03-23"  # Фиксируем для совместимости
        df['Is_Holiday_Period'] = df.get('Location', 'RU').apply(lambda loc: check_holidays(loc, current_date))
        
        # Генерация рекомендаций
        if os.getenv('OPENAI_API_KEY'):
            df['Recommendation'] = df.apply(get_ai_recommendation, axis=1)
        else:
            df['Recommendation'] = generate_basic_recommendation(df)
        
        return df
        
    except Exception as e:
        logger.error(f"Ошибка обработки данных: {str(e)}")
        raise

def parse_history(value):
    """
    Парсинг истории цен или продаж из различных форматов.
    
    Args:
        value: Значение для парсинга (строка или список)
        
    Returns:
        list: Список значений
    """
    if pd.isna(value):
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            try:
                return ast.literal_eval(value)
            except (SyntaxError, ValueError):
                return [float(x.strip()) for x in value.split(',') if x.strip()]
    return [value]

def calculate_price_sensitivity(row, metric_type):
    """
    Расчет чувствительности к изменению цены.
    
    Args:
        row: Строка данных
        metric_type: Тип метрики ('units' или 'revenue')
        
    Returns:
        float: Значение чувствительности
    """
    try:
        price_history = row['Price_History']
        sales_history = row['Sales_History']
        
        if len(price_history) < 2 or len(sales_history) < 2:
            return 0
        
        last_price, prev_price = price_history[-1], price_history[-2]
        last_sales, prev_sales = sales_history[-1], sales_history[-2]
        
        price_diff = last_price - prev_price
        if price_diff == 0:
            return 0
        
        if metric_type == 'units':
            return (last_sales - prev_sales) / price_diff
        else:  # revenue
            return (last_sales * last_price - prev_sales * prev_price) / price_diff
            
    except Exception as e:
        logger.warning(f"Ошибка расчета чувствительности: {str(e)}")
        return 0

def check_holidays(location, current_date="2025-03-23"):
    """
    Проверка близости праздников.
    
    Args:
        location: Код страны ('RU', 'US', etc.)
        current_date: Дата для проверки (по умолчанию 2025-03-23)
        
    Returns:
        bool: True если праздник близко, иначе False
    """
    try:
        current = datetime.strptime(current_date, '%Y-%m-%d')
        holiday_dict = {'US': holidays.US(years=2025), 'RU': holidays.RU(years=2025)}
        country_holidays = holiday_dict.get(location.upper(), holidays.RU(years=2025))
        
        for i in range(8):  # 7 дней вперед + текущий
            check_date = current + timedelta(days=i)
            if check_date in country_holidays:
                return True
        return False
        
    except Exception as e:
        logger.warning(f"Ошибка проверки праздников: {str(e)}")
        return False

def get_ai_recommendation(row):
    """
    Получение рекомендаций от OpenAI с учетом безопасности.
    
    Args:
        row: Строка данных
        
    Returns:
        str: Рекомендация
    """
    try:
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            logger.warning("API ключ OpenAI не найден в переменных окружения")
            return "API ключ OpenAI не настроен"
        
        # Безопасно формируем промпт без чувствительных данных
        prompt = f"""
        На основе метрик товара "{row.get('Product', 'Товар')}":
        - Current_Price: {row.get('Current_Price', 'N/A')}
        - Cost: {row.get('Cost', 'N/A')}
        - Current_Stock: {row.get('Current_Stock', 'N/A')}
        - Sales_30d: {row.get('Sales_30d', 'N/A')}
        - Sales_Velocity: {row.get('Sales_Velocity', 'N/A'):.2f}
        - Stock_Runway: {row.get('Stock_Runway', 'N/A'):.1f}
        - Discount_Margin: {row.get('Discount_Margin', 'N/A'):.1f}
        - Competitor_Gap: {row.get('Competitor_Gap', 'N/A'):.1f}
        - PS_units: {row.get('PS_units', 'N/A'):.2f}
        - PS_revenue: {row.get('PS_revenue', 'N/A'):.2f}
        - Seasonal_Demand_Factor: {row.get('Seasonal_Demand_Factor', 'N/A'):.2f}
        - Is_Holiday_Period: {'Yes' if row.get('Is_Holiday_Period', False) else 'No'}
        Предложи акцию в формате:
        1. Краткий анализ (1-2 предложения)
        2. Рекомендация
        3. Ожидаемый эффект
        """
        
        # Скрываем API ключ из логирования
        logger.info(f"Отправка запроса к OpenAI API для товара {row.get('Product', 'Неизвестный')}")
        
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": "gpt-3.5-turbo",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 150
            },
            timeout=10
        )
        
        # Проверка ошибок без логирования полного ответа
        response.raise_for_status()
        result = response.json()
        
        if 'choices' not in result or len(result['choices']) == 0:
            logger.error("Неожиданный формат ответа от OpenAI API")
            return "Ошибка формата ответа от API"
            
        return result['choices'][0]['message']['content']
        
    except requests.exceptions.RequestException as e:
        # Логируем ошибку без полного стека и API ключа
        error_msg = str(e)
        safe_error = error_msg.replace(api_key, "***API_KEY***") if api_key in error_msg else error_msg
        logger.error(f"Ошибка OpenAI: {safe_error}")
        return "Ошибка связи с OpenAI API"
    except Exception as e:
        # Общий случай: убеждаемся, что API ключ не попадает в логи
        error_msg = str(e)
        safe_error = error_msg.replace(api_key, "***API_KEY***") if api_key and api_key in error_msg else error_msg
        logger.error(f"Непредвиденная ошибка: {safe_error}")
        return "Непредвиденная ошибка при генерации рекомендации"

def generate_basic_recommendation(df):
    """
    Генерация базовых рекомендаций без AI.
    
    Args:
        df: DataFrame с данными
        
    Returns:
        pandas.Series: Рекомендации
    """
    def basic_logic(row):
        stock_runway = row.get('Stock_Runway', 0)
        ps_units = row.get('PS_units', 0)
        is_holiday = row.get('Is_Holiday_Period', False)
        
        if stock_runway > 60 and ps_units < -0.1:
            return "Анализ: Избыточные запасы и высокая чувствительность к цене.\nРекомендация: Скидка 15%.\nЭффект: Ускорение продаж."
        elif stock_runway < 15:
            return "Анализ: Низкие запасы.\nРекомендация: Повысить цену на 10%.\nЭффект: Сохранение запасов."
        elif is_holiday:
            return "Анализ: Приближается праздник.\nРекомендация: Скидка 10%.\nЭффект: Рост продаж."
        else:
            return "Анализ: Стабильная ситуация.\nРекомендация: Сохранить цену.\nЭффект: Стабильность."
    
    return df.apply(basic_logic, axis=1)

def format_price(price):
    """
    Функция для форматирования цены
    """
    return f"{price:.2f}" 