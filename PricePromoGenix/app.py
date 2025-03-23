from flask import Flask, request, render_template, jsonify, redirect, url_for, Response, send_file
import pandas as pd
import logging
import os
import io
from datetime import datetime
from dotenv import load_dotenv
from utils import process_data
from config import Config, logger
from werkzeug.utils import secure_filename

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Загрузка переменных окружения
load_dotenv()

app = Flask(__name__)
app.config.from_object(Config)

# Глобальное хранилище данных
data_store = {
    'raw_data': None,
    'processed_data': None,
    'last_update': None
}

@app.before_request
def security_check():
    """Проверки безопасности перед обработкой запроса."""
    # Проверка на подозрительные запросы
    if request.path.startswith('/.env') or '.env' in request.path:
        logger.warning(f"⚠️ Подозрительный запрос к {request.path} от {request.remote_addr}")
        return "Доступ запрещен", 403
    
    # Логируем все запросы
    logger.info(f"📝 {request.method} {request.path} от {request.remote_addr}")

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        if 'file' not in request.files:
            return render_template('index.html', error='Файл не выбран')
        
        file = request.files['file']
        if file.filename == '':
            return render_template('index.html', error='Файл не выбран')
        
        try:
            # Определение типа файла
            if file.filename.endswith('.csv'):
                data = pd.read_csv(file)
            elif file.filename.endswith(('.xlsx', '.xls')):
                data = pd.read_excel(file)
            else:
                return render_template('index.html', error='Поддерживаются только файлы CSV и Excel')
            
            # Сохранение сырых данных
            data_store['raw_data'] = data
            
            # Обработка данных - process_data уже включает генерацию рекомендаций
            processed_data = process_data(data)
            data_store['processed_data'] = processed_data
            
            # Обновление времени
            data_store['last_update'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            return render_template(
                'index.html', 
                table=processed_data.to_html(classes='table table-striped'),
                success=True,
                last_update=data_store['last_update']
            )
            
        except Exception as e:
            logger.error(f"Ошибка при обработке файла: {str(e)}")
            return render_template('index.html', error=f'Ошибка: {str(e)}')
    
    return render_template('index.html')

@app.route('/api/upload', methods=['POST'])
def api_upload():
    try:
        # Проверяем формат данных
        if request.is_json:
            data_json = request.get_json()
            data = pd.DataFrame(data_json)
        else:
            # Обработка формы с файлом
            if 'file' not in request.files:
                return jsonify({"error": "Файл не найден"}), 400
            
            file = request.files['file']
            if file.filename.endswith('.csv'):
                data = pd.read_csv(file)
            elif file.filename.endswith(('.xlsx', '.xls')):
                data = pd.read_excel(file)
            else:
                return jsonify({"error": "Поддерживаются только файлы CSV и Excel"}), 400
        
        # Обработка данных через единую функцию process_data,
        # которая также генерирует рекомендации
        processed_data = process_data(data)
        
        # Обновление хранилища
        data_store['raw_data'] = data
        data_store['processed_data'] = processed_data
        
        # Обновление времени
        data_store['last_update'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        return jsonify({
            "success": True,
            "data": processed_data.to_dict(orient='records'),
            "last_update": data_store['last_update']
        })
        
    except Exception as e:
        logger.error(f"Ошибка API: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/data', methods=['GET'])
def get_data():
    if data_store['processed_data'] is None:
        return jsonify({"error": "Нет обработанных данных"}), 404
    
    return jsonify({
        "data": data_store['processed_data'].to_dict(orient='records'),
        "last_update": data_store['last_update']
    })

@app.route('/api/export', methods=['GET'])
def export_data():
    if data_store['processed_data'] is None:
        return jsonify({"error": "Нет данных для экспорта"}), 404
    
    format_type = request.args.get('format', 'csv')
    
    try:
        if format_type == 'csv':
            csv_data = data_store['processed_data'].to_csv(index=False)
            return Response(
                csv_data,
                mimetype="text/csv",
                headers={"Content-disposition": f"attachment; filename=price_actions_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"}
            )
        elif format_type == 'excel':
            # Создаем буфер для Excel файла
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                data_store['processed_data'].to_excel(writer, sheet_name='Data', index=False)
            output.seek(0)
            
            return send_file(
                output,
                mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                as_attachment=True,
                download_name=f"price_actions_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
            )
        elif format_type == 'json':
            return jsonify(data_store['processed_data'].to_dict(orient='records'))
        else:
            return jsonify({"error": "Неподдерживаемый формат экспорта"}), 400
    except Exception as e:
        logger.error(f"Ошибка экспорта данных: {str(e)}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000) 