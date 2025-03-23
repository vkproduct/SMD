from flask import Flask, render_template, request, Response, jsonify
from dotenv import load_dotenv
import os
import pandas as pd
from werkzeug.utils import secure_filename
from datetime import datetime
import logging
from utils import process_data
import io

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Конфигурация для загрузки файлов
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max-limit

# Создаем директорию для загрузок, если её нет
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Глобальное хранилище данных
data_store = {
    'raw_data': None,
    'processed_data': None,
    'full_data': None,  # для хранения всех метрик
    'last_update': None
}

def allowed_file(filename):
    """Проверка расширения файла."""
    ALLOWED_EXTENSIONS = {'csv', 'xlsx', 'xls'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        if 'file' not in request.files or not request.files['file'].filename:
            return render_template('index.html', error='Файл не выбран', data_store=data_store)
        
        file = request.files['file']
        if not file.filename.endswith(('.csv', '.xlsx', '.xls')):
            return render_template('index.html', error='Поддерживаются только файлы CSV и Excel', data_store=data_store)
        
        try:
            if file.filename.endswith('.csv'):
                data = pd.read_csv(file)
            else:
                data = pd.read_excel(file)
            
            # Сохраняем сырые данные
            data_store['raw_data'] = data
            
            # Обрабатываем данные для отображения
            processed_data = process_data(data)
            
            # Создаем упрощенную таблицу для основного отображения
            simple_columns = ['Product', 'Current_Price', 'Cost', 'Current_Stock', 'Sales_30d', 'Competitor_Price', 'History', 'Recommendation']
            simple_table = processed_data[simple_columns].copy()
            
            # Сохраняем обработанные данные
            data_store['processed_data'] = processed_data
            data_store['last_update'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            logger.info(f"Файл {file.filename} обработан, строк: {len(processed_data)}")
            
            return render_template(
                'index.html',
                table=simple_table.to_html(classes='table table-striped', index=False),
                success=True,
                last_update=data_store['last_update'],
                data_store=data_store
            )
        except Exception as e:
            logger.error(f"Ошибка: {str(e)}")
            data_store['processed_data'] = None
            return render_template('index.html', error=f'Ошибка: {str(e)}', data_store=data_store)
    
    return render_template('index.html', data_store=data_store)

@app.route('/api/full_data', methods=['GET'])
def full_data():
    if data_store['raw_data'] is None:
        return jsonify({"error": "Нет данных"}), 404
    
    # Получаем полные данные с историей
    full_df = process_data(data_store['raw_data'])
    
    # Добавляем все метрики
    full_df['Sales_Velocity'] = (full_df['Sales_30d'] / 30).round(2)
    full_df['Stock_Runway'] = (full_df['Current_Stock'] / full_df['Sales_Velocity']).round(1)
    full_df['Discount_Margin'] = ((full_df['Current_Price'] - full_df['Cost']) / full_df['Current_Price'] * 100).round(1)
    full_df['Competitor_Gap'] = ((full_df['Current_Price'] - full_df['Competitor_Price']) / full_df['Competitor_Price'] * 100).round(1)
    
    # Добавляем исторические данные, если они есть
    if 'Price_History' in data_store['raw_data'].columns and 'Sales_History' in data_store['raw_data'].columns:
        full_df['Price_History'] = data_store['raw_data']['Price_History']
        full_df['Sales_History'] = data_store['raw_data']['Sales_History']
    
    return jsonify(full_df.to_dict(orient='records'))

@app.route('/api/export', methods=['GET'])
def export_data():
    format_type = request.args.get('format', 'json')
    
    if data_store['processed_data'] is None:
        return jsonify({"error": "Нет данных для экспорта"}), 404
    
    if format_type == 'csv':
        return Response(
            data_store['processed_data'].to_csv(index=False),
            mimetype='text/csv',
            headers={"Content-Disposition": "attachment;filename=export.csv"}
        )
    elif format_type == 'excel':
        output = io.BytesIO()
        data_store['processed_data'].to_excel(output, index=False)
        output.seek(0)
        return Response(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            headers={"Content-Disposition": "attachment;filename=export.xlsx"}
        )
    
    # По умолчанию возвращаем JSON
    return jsonify(data_store['processed_data'].to_dict(orient='records'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True) 