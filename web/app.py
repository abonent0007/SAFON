"""
Flask веб-приложение С.А.Ф.О.Н. — прогнозирование событий на основе ансамбля методик
"""

import os
import re
import sys
import threading
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
from core.config import get_categories  # noqa: E402

load_dotenv()

EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


def create_app(config=None):
    app = Flask(__name__)
    CORS(app)
    
    app.config['PREDICTION_THRESHOLD'] = float(os.getenv('HIGH_IMPORTANCE_THRESHOLD', 0.75))
    app.config['PREDICTION_HORIZON'] = int(os.getenv('PREDICTION_HORIZON', 80))
    app.config['NOTIFICATION_EMAIL'] = os.getenv('NOTIFICATION_EMAIL', '')
    
    # Инициализация БД
    db = SafonDatabase()
    assert db.conn is not None
    db.load_historical_data()
    
    # Инициализация DeepSeek и анализатора
    analyzer = UltimateSemanticAnalyzer()
    predictor = PredictionEngine(db, analyzer)
    astro = AstrometryModule()

    # Регенерация предсказаний при каждом запуске (активное окно пересоздаётся)
    _safe_print("\n⚡ Генерация предсказаний (с учётом -5 лет валидации)...")
    predictor.generate_predictions(
        horizon=app.config['PREDICTION_HORIZON'],
        use_astrometry=True, use_ai=False
    )
    _safe_print(f"✅ {len(db.get_active_predictions())} предсказаний готово")
    
    # Email нотификатор
    email_notifier = None
    smtp_user = os.getenv('SMTP_USERNAME', '')
    smtp_pass = os.getenv('SMTP_PASSWORD', '')
    if smtp_user and smtp_pass:
        email_notifier = EmailNotifier(
            smtp_server=os.getenv('SMTP_SERVER', 'smtp.gmail.com'),
            smtp_port=int(os.getenv('SMTP_PORT', '587') or 587),
            username=smtp_user,
            password=smtp_pass
        )

    # Обогатитель истории через интернет-поиск
    enricher = HistoryEnricher(db, get_deepseek_engine())

    # Блокировки тяжёлых операций: параллельные POST недопустимы (409)
    job_locks = {name: threading.Lock() for name in ('regenerate', 'enrich', 'backtest', 'astrometry')}

    def _busy(name):
        return jsonify({'status': 'error', 'message': f'Операция «{name}» уже выполняется'}), 409

    def _get_int(data, key, default, lo, hi):
        try:
            value = int(data.get(key, default))
        except (TypeError, ValueError):
            return None
        return value if lo <= value <= hi else None
    
    @app.route('/')
    def index():
        return render_template('index.html')

    @app.route('/api/config')
    def get_config_api():
        """Динамический конфиг для UI: категории (цвета/иконки/формы), порог, горизонт."""
        return jsonify({
            'categories': get_categories(),
            'threshold': app.config['PREDICTION_THRESHOLD'],
            'horizon': app.config['PREDICTION_HORIZON'],
        })

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
        if not job_locks['regenerate'].acquire(blocking=False):
            return _busy('regenerate')
        try:
            _safe_print("🔄 Обновление предсказаний (DeepSeek AI)...")
            data = request.json or {}
            use_astrometry = bool(data.get('use_astrometry', True))
            use_ai = bool(data.get('use_ai', True))

            new_predictions = predictor.generate_predictions(
                horizon=app.config['PREDICTION_HORIZON'],
                use_astrometry=use_astrometry, use_ai=use_ai
            )

            if email_notifier and app.config['NOTIFICATION_EMAIL']:
                important = [p for p in new_predictions if p['probability'] >= app.config['PREDICTION_THRESHOLD']]
                if important:
                    for email in app.config['NOTIFICATION_EMAIL'].split(','):
                        ok, msg = email_notifier.send_important_predictions(email.strip(), important)
                        if not ok:
                            _safe_print(f"⚠️ Email ({email.strip()}): {msg}")

            return jsonify({'status': 'success', 'message': f'Сгенерировано {len(new_predictions)} предсказаний (AI: {use_ai})'})
        finally:
            job_locks['regenerate'].release()
    
    @app.route('/api/send-email', methods=['POST'])
    def send_email():
        if not email_notifier:
            return jsonify({'status': 'error', 'message': 'Email не настроен'}), 500
        data = request.json or {}
        recipient = data.get('email') or app.config['NOTIFICATION_EMAIL']
        if not recipient:
            return jsonify({'status': 'error', 'message': 'Email не указан'}), 400
        recipient = str(recipient).strip()
        if not EMAIL_RE.match(recipient):
            return jsonify({'status': 'error', 'message': 'Некорректный адрес email'}), 400
        predictions = db.get_important_predictions(app.config['PREDICTION_THRESHOLD'])
        ok, msg = email_notifier.send_important_predictions(recipient, predictions)
        if ok:
            return jsonify({'status': 'success', 'message': 'Email отправлен'})
        return jsonify({'status': 'error', 'message': f'Ошибка отправки: {msg}'}), 500
    
    @app.route('/api/astrometry/status')
    def astrometry_status():
        return jsonify(predictor.get_astrometry_status())
    
    @app.route('/api/astrometry/correlations')
    def astrometry_correlations():
        correlations = db.get_astrometry_correlations()
        return jsonify({'correlations': correlations})
    
    @app.route('/api/astrometry/analyze', methods=['POST'])
    def analyze_astrometry():
        if not job_locks['astrometry'].acquire(blocking=False):
            return _busy('astrometry')
        try:
            correlations = predictor.analyze_astrometry_correlations()
            return jsonify({'status': 'success', 'correlations_found': len(correlations) if correlations else 0})
        finally:
            job_locks['astrometry'].release()
    
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
        """Статус DeepSeek"""
        return jsonify(analyzer.get_status())
    
    @app.route('/api/ai/analyze', methods=['POST'])
    def ai_analyze():
        """Ручной анализ события через DeepSeek"""
        data = request.json or {}
        title = str(data.get('title', '')).strip()
        if not title:
            return jsonify({'status': 'error', 'message': 'Поле title обязательно'}), 400
        description = str(data.get('description', ''))
        year = _get_int(data, 'year', 2024, 1, 3000)
        if year is None:
            return jsonify({'status': 'error', 'message': 'Некорректный год (1-3000)'}), 400

        result = analyzer.analyze(title, description, year)
        return jsonify(result)

    @app.route('/api/backtest', methods=['POST'])
    def run_backtest():
        """Запускает walk-forward бэктестинг и автокоррекцию циклов"""
        if not job_locks['backtest'].acquire(blocking=False):
            return _busy('backtest')
        try:
            data = request.json or {}
            from_year = _get_int(data, 'from_year', 2000, 1800, 2100)
            if from_year is None:
                return jsonify({'status': 'error', 'message': 'Некорректный from_year (1800-2100)'}), 400
            result = predictor.run_backtest(from_year=from_year)
            adjusted = predictor.auto_correct_cycles()
            return jsonify({
                'status': 'success',
                'total_accuracy': result['total_accuracy'],
                'year_hit_rate': result.get('year_hit_rate', result['total_accuracy']),
                'location_hit_rate': result.get('location_hit_rate', 0),
                'brier_score': result.get('brier_score', 0),
                'by_category': result['by_category'],
                'cycles_adjusted': adjusted,
            })
        finally:
            job_locks['backtest'].release()

    @app.route('/api/backtest/accuracy')
    def backtest_accuracy():
        """Возвращает результаты последнего бэктестинга"""
        cursor = db.conn.execute("""
            SELECT category,
                   COUNT(*) as total,
                   SUM(CASE WHEN status='confirmed' OR status='partial' THEN 1 ELSE 0 END) as hits
            FROM backtest_results GROUP BY category
        """)
        rows = [dict(r) for r in cursor.fetchall()]
        result = {}
        for r in rows:
            result[r['category']] = {
                'total': r['total'],
                'hits': r['hits'],
                'accuracy': round(r['hits'] / r['total'], 2) if r['total'] else 0,
            }
        return jsonify(result)

    @app.route('/api/historical')
    def get_historical():
        """Реальные исторические события за последние N лет (по умолчанию 5)"""
        from datetime import datetime
        years = _get_int(request.args.to_dict(), 'years', 5, 1, 100)
        if years is None:
            return jsonify({'status': 'error', 'message': 'Некорректный параметр years (1-100)'}), 400
        events = db.get_all_events()
        now = datetime.now().year
        recent = [e for e in events if now - years <= e['year'] <= now]
        return jsonify([{
            'year': e['year'], 'category': e['category'],
            'location': e.get('location', ''), 'title': e.get('title', ''),
            'lat': e.get('lat', 0), 'lng': e.get('lng', 0),
        } for e in recent])

    @app.route('/api/enrich', methods=['POST'])
    def enrich_history():
        """Автоматический поиск исторических событий (многопоточно + датасеты)"""
        data = request.json or {}
        max_per_category = _get_int(data, 'max_per_category', 10, 1, 40)
        workers = _get_int(data, 'workers', 6, 1, 16)
        if max_per_category is None or workers is None:
            return jsonify({'status': 'error',
                            'message': 'Некорректные параметры: max_per_category 1-40, workers 1-16'}), 400
        use_ai = bool(data.get('use_ai', True))

        if not job_locks['enrich'].acquire(blocking=False):
            return _busy('enrich')
        prev_deepseek = enricher.deepseek
        if not use_ai:
            enricher.deepseek = None
        try:
            # 1. Структурированные датасеты (USGS, NOAA)
            from core.data_sources import USGSFetcher, NOAAFetcher
            USGSFetcher().populate_db(db, max_events=300)
            NOAAFetcher().populate_db(db)

            # 2. Интернет-поиск (Wikipedia + DuckDuckGo)
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
        finally:
            enricher.deepseek = prev_deepseek
            job_locks['enrich'].release()

    return app


if __name__ == '__main__':
    app = create_app()
    
    _safe_print("\n" + "="*60)
    _safe_print("   С.А.Ф.О.Н. с DeepSeek запущен!")
    _safe_print("="*60)
    
    # Проверка DeepSeek
    deepseek = get_deepseek_engine()
    status = deepseek.get_system_status()
    _safe_print("\n🤖 DeepSeek статус:")
    _safe_print(f"   Режим: {status['mode']}")
    _safe_print(f"   Модель: {status['model']}")
    _safe_print(f"   Доступность: {'✅ Да' if status['available'] else '❌ Нет'}")
    
    if status['mode'] == 'lm-studio' and not status['available']:
        _safe_print("\n   ⚠️ ВНИМАНИЕ: LM Studio не запущен!")
        _safe_print("   → Запустите LM Studio")
        _safe_print("   → Загрузите модель DeepSeek в LM Studio")
        _safe_print("   → Нажмите 'Start Local Inference Server'")
    elif status['mode'] == 'api' and not status['available']:
        _safe_print("   ⚠️ ВНИМАНИЕ: API ключ не настроен!")
        _safe_print("   → Добавьте DEEPSEEK_API_KEY в файл .env")
    
    host = os.getenv('SERVER_HOST', '0.0.0.0')
    try:
        port = int(os.getenv('SERVER_PORT', '5000'))
    except ValueError:
        port = 5000

    _safe_print(f"\n🌐 Веб-интерфейс: http://localhost:{port}")
    _safe_print("="*60)

    import webbrowser
    threading.Timer(2.0, lambda: webbrowser.open(f'http://localhost:{port}')).start()

    app.run(host=host, port=port, debug=False)
