# Changelog

## v4.3 — Audit & Dynamic Data Refactor

### Устранённые логические пробелы
- Активное окно предсказаний пересоздаётся целиком — устаревшие прогнозы старых якорей больше не накапливаются
- Автокоррекции периодов (`cycle_adjustments`) стали персистентными: применяются при каждой генерации (`_load_cycles`), а не теряются при рестарте
- Параллельные тяжёлые POST (`regenerate`/`enrich`/`backtest`/`astrometry`) защищены блокировками → 409 вместо гонок и «database is locked»
- Валидация API-параметров: email (regex), from_year, years, workers, max_per_category, title, year → 400 с пояснением
- Email-ошибки больше не глотаются: `send_important_predictions` → (ok, message); ошибки логируются
- `enricher.deepseek` восстанавливается после enrich без AI (раньше AI-режим отключался навсегда)
- SQLite `timeout=30` — устойчивость под многопоточным Flask
- Обогащение: детерминированный шаг поиска пробелов (был random 15–25); ошибки AI-разбора логируются
- Удалён застаревший артефакт автокоррекции (землетрясение 8→22 при «точности 0.0» — от старой метрики)

### Хардкод → динамические данные
- `config/safon_config.json` (новый): категории (цвет/иконка/shape/важность), 106 локаций, 11 циклов, описания, сезонные месяцы, контексты, шаблоны обогащения
- `core/config.py` — загрузчик с авто-перезагрузкой по mtime: правки конфига подхватываются без рестарта
- `config/seed_events.json` — 677 стартовых событий вынесены из кода (database.py: 1298 → 372 строк)
- UI: `/api/config` + динамические цвета/иконки/формы категорий и порог в тексте (хардкод-карты удалены из index.html)
- Веб-сервер: `SERVER_HOST`/`SERVER_PORT` из окружения

### Тесты
- `tests/` (unittest): 35 тестов — конфиг, БД/сид/миграции, детерминизм ансамбля и границы, очистка устаревших прогнозов, цепочки, walk-forward+lift, валидация API, email-ошибки. Все зелёные.

### UI / Карта / Фильтр (по обратной связи)
- Карта переведена на **полностью офлайн-режим**: self-hosted Leaflet (`web/static/vendor/leaflet/`) + локальный GeoJSON границ стран (`web/static/data/world.geojson`) — внешние CDN (unpkg) и тайл-серверы (cartocdn) больше не используются; 0 внешних запросов
- Фильтр перенесён из «ниоткуда» к фильтруемому списку (внутри секции карты, над списком событий); выбор фильтра сохраняется между автообновлениями; фильтры и таймлайн обновляются даже при сбое рендера списка
- Цвета маркеров карты — из конфига (последний хардкод-дубль removed)
- Вычищены остатки «DeepSeek V4 Pro» из UI, README, САФОН.md, модулей и bat-файлов; favicon; консоль страницы чистая

## v4.2 — Multi-Method Ensemble Update

### Prediction Core
- **Ансамбль методик**: вероятность = цикл (0.40) + спектральный анализ (0.25) + астрометрия (0.15) + причинные цепочки (0.10) + walk-forward калибровка (0.10) + бонус согласия методик
- **Причинные цепочки подключены** к конвейеру (A→B через N лет; правила в `cross_category_rules`)
- **Walk-forward бэктест**: точность года ±1, локация, Brier score и **lift к случайному году** (колонка `backtest_results.lift`)
- **Калибровка**: индекс согласия методик → вероятность (верхний хвост усиливается, низ не искажается)
- **Объяснимость**: обоснование каждого прогноза содержит вклад всех методик
- **Детерминизм**: убран random из вероятностей и месяцев — прогнозы воспроизводимы

### Fixes
- Краш cp1251 устранён: все raw-print → `_safe_print` (astrometry, analyzer, deepseek_engine)
- Сезонная декомпозиция месяца реально подключена (была мёртвым кодом)
- Убран двойной AI-проход при генерации (одна точка улучшения, экономия вызовов)
- `cross_category`: set-оптимизация анализа (быстрее в разы, та же семантика)

### DeepSeek
- Актуальная модель `deepseek-flash` (V4.1) для API-режима; `deepseek-v4-pro` остаётся опцией
- Thinking-режим: `DEEPSEEK_THINKING=enabled|disabled`, `DEEPSEEK_REASONING_EFFORT=low|high|max`
- Base URL выровнен под актуальные доки: `https://api.deepseek.com/chat/completions` (без /v1); таймаут 120с
- JSON-режим (`response_format: json_object`) для классификации событий — надёжный парсинг
- Живой smoke-тест соединения: `scripts/test_api_connection.py` (ответ за 1.7с, JSON-классификация OK)

### Infrastructure
- Инициализирован git-репозиторий (+ baseline-коммит), `.gitignore`
- `requirements.txt`: удалены неиспользуемые torch/transformers/sentence-transformers/numpy (~5 ГБ)
- Утилиты: `scripts/import_intern_2019_2024.py`, `regen_predictions.py`, `run_backtest.py`, `cleanup_stale_predictions.py`

### Data
- +75 исторических событий 2019–2024 (append-only импорт, дедупликация, 1 фантом исключён)
- Новые якоря циклов: цунами 2018→2024, засуха 2019→2023, эпидемия/революция/эко 2020→2023, война 2022→2024

## v4.1 — Analitical Precision Update

### New Features
- **Backtesting** — verify prediction accuracy against historical data (`POST /api/backtest`)
- **Auto-correction** — cycles auto-adjust when backtest accuracy < 40%
- **USGS Earthquake Catalog** — 300+ earthquakes M≥6.0 from 1900 (free API)
- **NOAA Hurricane Database** — 80+ Atlantic hurricanes 1851-2024 (HURDAT2)
- **Spectral Analyzer** — FFT-based hidden period detection
- **Cross-category chains** — trigger events boost related predictions (A→B after N years)
- **Weighted cycles** — recent events + high magnitude = higher weight
- **Seasonal decomposition** — month prediction based on real event distribution
- **Accuracy Panel** — per-category accuracy bars with hit/miss counts
- **Event Detail Modal** — click any event card for full analysis
- **Database migration** — 4 new tables via ALTER/CREATE IF NOT EXISTS

### UI Improvements
- **Glassmorphism** — backdrop-filter blur on all panels
- **SVG icons** — 11 intuitive pictograms replacing emojis
- **Category-colored borders** — each detail card tinted to its category
- **Radial gradient background** — atmospheric depth effect
- **Operation status bar** — animated progress during long operations
- **Button locking** — prevents double-clicks during operations

### Predictions
- Horizon expanded to include 5 years before current year (validation window)
- Threshold lowered to 70% for broader coverage
- Astrometry boost-only mode (never penalizes)
- UPSERT predictions (no duplicates)

### Database
- Built-in events: 24 → 677 (+2733%)
- Categories: 7 → 11
- Historical range: 1906-2023 → 64 CE - 2023 (1959 years)

## v4.0 — Initial Release

### Core
- Flask web server with REST API
- SQLite database with event/prediction tables
- DeepSeek V4 Pro integration (API + LM Studio)
- Skyfield astrometry module
- Fractal cycle detection (5 scales)

### Interface
- Google Maps integration → replaced with Leaflet.js (free)
- Key events panel
- Causal analysis section
- Timeline (100 years)
- Email notifications
- Filters by country and category

### Data
- 24 built-in historical events
- Wikipedia + DuckDuckGo enrichment
- Multithreaded search (6 workers)
