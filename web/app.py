"""
Flask веб-приложение С.А.Ф.О.Н. с DeepSeek V4 Pro
"""

import os
import sys
from pathlib import Path

from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv


def _safe_print(message):
    try:
        print(message)
    except UnicodeEncodeError:
        print(message.encode('ascii', errors='replace').decode('ascii'))

sys.path.insert(0, str(Path(__file__).parent.parent))  # noqa: E402

from core.database import SafonDatabase  # noqa: E402
from core.predictor import PredictionEngine  # noqa: E402
from core.email_notifier import EmailNotifier  # noqa: E402
from core.analyzer import UltimateSemanticAnalyzer  # noqa: E402
from core.deepseek_engine import get_deepseek_engine  # noqa: E402
from core.astrometry import AstrometryModule  # noqa: E402
from core.history_enricher import HistoryEnricher  # noqa: E402

load_dotenv()

def create_app(config: dict = None):
    app = Flask(__name__)
    CORS(app)
    
    app.config['PREDICTION_THRESHOLD'] = float(os.getenv('HIGH_IMPORTANCE_THRESHOLD', 0.75))
    app.config['PREDICTION_HORIZON'] = int(os.getenv('PREDICTION_HORIZON', 80))
    app.config['NOTIFICATION_EMAIL'] = os.getenv('NOTIFICATION_EMAIL', '')
    
    # Инициализация БД
    db = SafonDatabase()
    db.load_historical_data()
    
    # Инициализация DeepSeek и анализатора
    analyzer = UltimateSemanticAnalyzer()
    predictor = PredictionEngine(db, analyzer)
    astro = AstrometryModule()

    # Генерация предсказаний только при первом запуске (пустая БД)
    existing = db.get_active_predictions()
    if not existing:
        _safe_print("\n⚡ Первый запуск — генерация предсказаний...")
        predictor.generate_predictions(
            horizon=app.config['PREDICTION_HORIZON'],
            use_astrometry=True, use_ai=False
        )
        _safe_print(f"✅ Сгенерировано {len(db.get_active_predictions())} предсказаний")
    else:
        _safe_print(f"\n📊 Загружено {len(existing)} предсказаний из БД")
    
    # Email нотификатор
    email_notifier = None
    if os.getenv('SMTP_USERNAME') and os.getenv('SMTP_PASSWORD'):
        email_notifier = EmailNotifier(
            smtp_server=os.getenv('SMTP_SERVER', 'smtp.gmail.com'),
            smtp_port=int(os.getenv('SMTP_PORT', 587)),
            username=os.getenv('SMTP_USERNAME'),
            password=os.getenv('SMTP_PASSWORD')
        )

    # Обогатитель истории через интернет-поиск
    enricher = HistoryEnricher(db, get_deepseek_engine())
    
    @app.route('/')
    def index():
        return render_template('index.html')
    
    @app.route('/api/predictions')
    def get_predictions():
        predictions = db.get_active_predictions()
        return jsonify({'predictions': predictions, 'total': len(predictions)})
    
    @app.route('/api/important')
    def get_important():
        predictions = db.get_important_predictions(app.config['PREDICTION_THRESHOLD'])
        return jsonify(predictions)
    
    @app.route('/api/locations')
    def get_locations():
        predictions = db.get_active_predictions()
        location_data = [{'lat': p['lat'], 'lng': p['lng'], 'category': p['category'], 
                          'year': p['predicted_year'], 'probability': p['probability'], 
                          'description': p.get('description', '')[:100], 'location': p.get('location', '')} 
                         for p in predictions[:50]]
        return jsonify(location_data)
    
    @app.route('/api/regenerate', methods=['POST'])
    def regenerate():
        _safe_print("🔄 Обновление предсказаний (DeepSeek AI)...")
        data = request.json or {}
        use_astrometry = data.get('use_astrometry', True)
        use_ai = data.get('use_ai', True)
        
        new_predictions = predictor.generate_predictions(
            horizon=app.config['PREDICTION_HORIZON'],
            use_astrometry=use_astrometry, use_ai=use_ai
        )
        
        if email_notifier and app.config['NOTIFICATION_EMAIL']:
            important = [p for p in new_predictions if p['probability'] >= app.config['PREDICTION_THRESHOLD']]
            if important:
                try:
                    for email in app.config['NOTIFICATION_EMAIL'].split(','):
                        email_notifier.send_important_predictions(email.strip(), important)
                except Exception:
                    pass
        
        return jsonify({'status': 'success', 'message': f'Сгенерировано {len(new_predictions)} предсказаний (AI: {use_ai})'})
    
    @app.route('/api/send-email', methods=['POST'])
    def send_email():
        if not email_notifier:
            return jsonify({'status': 'error', 'message': 'Email не настроен'}), 500
        recipient = request.json.get('email', app.config['NOTIFICATION_EMAIL'])
        if not recipient:
            return jsonify({'status': 'error', 'message': 'Email не указан'}), 400
        predictions = db.get_important_predictions(app.config['PREDICTION_THRESHOLD'])
        if email_notifier.send_important_predictions(recipient, predictions):
            return jsonify({'status': 'success', 'message': 'Email отправлен'})
        return jsonify({'status': 'error', 'message': 'Ошибка отправки'}), 500
    
    @app.route('/api/astrometry/status')
    def astrometry_status():
        return jsonify(predictor.get_astrometry_status())
    
    @app.route('/api/astrometry/correlations')
    def astrometry_correlations():
        correlations = db.get_astrometry_correlations()
        return jsonify({'correlations': correlations})
    
    @app.route('/api/astrometry/analyze', methods=['POST'])
    def analyze_astrometry():
        correlations = predictor.analyze_astrometry_correlations()
        return jsonify({'status': 'success', 'correlations_found': len(correlations) if correlations else 0})
    
    @app.route('/api/astrometry/year/<int:year>')
    def astrometry_for_year(year):
        """Возвращает астрометрические данные для указанного года"""
        try:
            data = {
                "year": year,
                "solar_phase": astro.get_solar_activity_phase(year),
                "lunar_phase": astro.get_lunar_phase(year, 6, 15),
                "active_correlations": astro.get_active_correlations(year)
            }
            return jsonify(data)
        except Exception as e:
            return jsonify({"error": str(e), "active_correlations": []})
    
    @app.route('/api/ai/status')
    def ai_status():
        """Статус DeepSeek V4 Pro"""
        return jsonify(analyzer.get_status())
    
    @app.route('/api/ai/analyze', methods=['POST'])
    def ai_analyze():
        """Ручной анализ события через DeepSeek"""
        data = request.json
        title = data.get('title', '')
        description = data.get('description', '')
        year = data.get('year', 2024)
        
        result = analyzer.analyze(title, description, year)
        return jsonify(result)

    @app.route('/api/enrich', methods=['POST'])
    def enrich_history():
        """Автоматический поиск исторических событий по циклическим паттернам (многопоточно)"""
        data = request.json or {}
        max_per_category = data.get('max_per_category', 10)
        workers = data.get('workers', 6)

        if not data.get('use_ai', True):
            enricher.deepseek = None

        result = enricher.enrich_all(max_per_category=max_per_category, workers=workers)

        # Быстрая регенерация без AI (AI — отдельной кнопкой)
        predictor.generate_predictions(
            horizon=app.config['PREDICTION_HORIZON'],
            use_astrometry=True, use_ai=False
        )

        return jsonify({
            'status': 'success',
            'total_added': result['total_added'],
            'by_category': result['by_category'],
            'sample': [{'year': e.get('year'), 'title': e.get('title')} for e in result['events'][:10]]
        })

    return app


if __name__ == '__main__':
    app = create_app()
    
    _safe_print("\n" + "="*60)
    _safe_print("   С.А.Ф.О.Н. с DeepSeek V4 Pro запущен!")
    _safe_print("="*60)
    
    # Проверка DeepSeek
    deepseek = get_deepseek_engine()
    status = deepseek.get_system_status()
    _safe_print("\n🤖 DeepSeek V4 Pro статус:")
    _safe_print(f"   Режим: {status['mode']}")
    _safe_print(f"   Модель: {status['model']}")
    _safe_print(f"   Доступность: {'✅ Да' if status['available'] else '❌ Нет'}")
    
    if status['mode'] == 'lm-studio' and not status['available']:
        _safe_print("\n   ⚠️ ВНИМАНИЕ: LM Studio не запущен!")
        _safe_print("   → Запустите LM Studio")
        _safe_print("   → Загрузите модель DeepSeek V4 Pro")
        _safe_print("   → Нажмите 'Start Local Inference Server'")
    elif status['mode'] == 'api' and not status['available']:
        _safe_print("   ⚠️ ВНИМАНИЕ: API ключ не настроен!")
        _safe_print("   → Добавьте DEEPSEEK_API_KEY в файл .env")
    
    _safe_print("\n🌐 Веб-интерфейс: http://localhost:5000")
    _safe_print("="*60)

    import webbrowser
    import threading
    threading.Timer(2.0, lambda: webbrowser.open('http://localhost:5000')).start()

    app.run(host='0.0.0.0', port=5000, debug=False)