# SAFON — Fractal-Causal Autonomous Prediction System

**С.А.Ф.О.Н.** — вероятностный исторический оракул, предсказывающий будущие события на основе анализа исторических циклов, причинно-следственных связей и астрометрических данных. Использует нейросеть **DeepSeek** (актуальная модель `deepseek-flash`) для генерации аналитических описаний и поиска скрытых паттернов.

## Quick Start

```batch
install.bat              # Python 3.11 + dependencies
run.bat                  # Launch server
```

Open: **http://localhost:5000**

## Features

- **677+ historical events** across 11 categories (64 CE — 2023)
- **80-year forecast horizon** with probability scoring
- **Interactive world map** (Leaflet.js + OpenStreetMap, free)
- **Timeline** with macOS Dock-style magnification (-5 / now / +95 years)
- **Country & category filters** with sort controls
- **AI causal analysis** — DeepSeek (`deepseek-flash`) generates detailed descriptions
- **Backtesting** with accuracy panel and cycle auto-correction
- **Auto-enrichment** — Wikipedia API + DuckDuckGo + USGS + NOAA
- **Multithreaded** — 6 parallel workers for enrichment
- **Email reports** — full HTML report with predictions
- **Glassmorphism UI** — dark theme with SVG category icons

## Categories

| Icon | Category | Events | Cycle |
|:----:|----------|:------:|:-----:|
| ▲ | Earthquakes | 116 | 8 years |
| ⬡ | Wars | 143 | 25 years |
| ◇ | Economic Crises | 74 | 11 years |
| ~ | Tsunamis | 21 | 12 years |
| 💧 | Floods | 55 | 7 years |
| 🔥 | Fires | 35 | 5 years |
| 🌀 | Hurricanes | 26 | 4 years |
| ✚ | Epidemics | 50 | 40 years |
| □ | Droughts | 94 | 12 years |
| ★ | Revolutions | 40 | 30 years |
| ☢ | Ecological Disasters | 23 | 8 years |

## Architecture

```
SAFON/
├── core/                     # Engine
│   ├── database.py           # SQLite + migration + JSON seed
│   ├── predictor.py          # Cycles + ensemble + walk-forward backtest
│   ├── deepseek_engine.py    # DeepSeek API / LM Studio
│   ├── config.py             # config loader (auto-reload)
│   ├── analyzer.py           # AI classification + enhancement
│   ├── astrometry.py         # Planetary correlations (Skyfield)
│   ├── history_enricher.py   # Wikipedia + DuckDuckGo search
│   ├── spectral_analyzer.py  # FFT period detection
│   ├── cross_category.py     # Cross-category chain rules
│   ├── email_notifier.py     # HTML email reports
│   └── data_sources/         # USGS + NOAA fetchers
├── web/                      # Frontend
│   ├── app.py                # Flask API (REST)
│   └── templates/
│       └── index.html        # Glassmorphism UI + timeline
└── data/                     # Runtime data (DO NOT DELETE)
    ├── safon.db              # SQLite database
    └── skyfield_data/        # NASA JPL ephemeris
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Main dashboard |
| GET | `/api/config` | UI config (categories, threshold) |
| GET | `/api/important` | Key events (prob ≥ 70%) |
| GET | `/api/predictions` | All active predictions |
| GET | `/api/locations` | Map marker data |
| POST | `/api/regenerate` | Regenerate with AI |
| POST | `/api/enrich` | Enrich DB (USGS+NOAA+Wiki+DDG) |
| POST | `/api/backtest` | Run backtesting |
| GET | `/api/backtest/accuracy` | Accuracy by category |
| GET | `/api/ai/status` | DeepSeek status |
| POST | `/api/send-email` | Email report |

## Configuration

Copy `.env.example` to `.env` and configure:

```env
DEEPSEEK_MODE=api           # api or lm-studio
DEEPSEEK_API_KEY=sk-...     # For api mode
HIGH_IMPORTANCE_THRESHOLD=0.70
PREDICTION_HORIZON=80
```

## Tech Stack

| Component | Technology |
|-----------|-----------|
| AI | DeepSeek: API (`deepseek-flash`) / LM Studio |
| Backend | Python 3.11 + Flask |
| Database | SQLite |
| Map | Leaflet.js (self-hosted) + offline GeoJSON |
| Astrometry | Skyfield (NASA JPL DE421) |
| Search | Wikipedia API + DuckDuckGo |
| Concurrency | ThreadPoolExecutor |

## License

MIT
