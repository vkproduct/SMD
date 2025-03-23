from app import app

if __name__ == "__main__":
    print("Запуск генератора ценовых акций...")
    print("Открой в браузере: http://localhost:5001")
    app.run(debug=True, host='0.0.0.0', port=5001) 