"""
Модуль интеграции с DeepSeek
Поддерживает:
- API DeepSeek (облачный, актуальная модель deepseek-flash; thinking-режим low/high/max)
- Локальный запуск через LM Studio (http://localhost:1234/v1)
"""

import os
import re
import json
import requests
from datetime import datetime
from typing import Dict, Optional

from .config import get_current_contexts


def _safe_print(message):
    try:
        print(message)
    except UnicodeEncodeError:
        print(message.encode('ascii', errors='replace').decode('ascii'))


class DeepSeekEngine:
    """Интеграция с DeepSeek через API (облачный или LM Studio)"""
    
    def __init__(self, config: Dict):
        self.mode = config.get('DEEPSEEK_MODE', 'lm-studio')
        
        # API DeepSeek (облачный)
        self.api_key = config.get('DEEPSEEK_API_KEY', '')
        self.api_url = config.get('DEEPSEEK_API_URL', 'https://api.deepseek.com')
        self.model = config.get('DEEPSEEK_MODEL', 'deepseek-flash')
        self.thinking = config.get('DEEPSEEK_THINKING', 'enabled')
        if self.thinking not in ('enabled', 'disabled'):
            self.thinking = 'enabled'
        self.reasoning_effort = config.get('DEEPSEEK_REASONING_EFFORT', 'high')
        if self.reasoning_effort not in ('low', 'high', 'max'):
            self.reasoning_effort = 'high'
        
        # LM Studio (локальный)
        self.lm_studio_url = config.get('LM_STUDIO_URL', 'http://localhost:1234/v1')
        self.lm_studio_model = config.get('LM_STUDIO_MODEL', 'deepseek-v4-pro')
        
        self._lm_studio_available = None
        
        used_model = self.lm_studio_model if self.mode == 'lm-studio' else self.model
        _safe_print(f"🤖 DeepSeek инициализация (режим: {self.mode}, модель: {used_model})")
        
        if self.mode == 'lm-studio':
            self._check_lm_studio()
    
    def _check_lm_studio(self) -> bool:
        """Проверяет доступность LM Studio"""
        try:
            response = requests.get(f"{self.lm_studio_url}/models", timeout=5)
            if response.status_code == 200:
                self._lm_studio_available = True
                _safe_print(f"   ✅ LM Studio обнаружен на {self.lm_studio_url}")
                return True
        except Exception as e:
            _safe_print(f"   ⚠️ LM Studio не доступен: {e}")
        
        self._lm_studio_available = False
        return False
    
    def _call_lm_studio(self, prompt: str, system_prompt: Optional[str] = None,
                        max_tokens: int = 2000, response_format: Optional[Dict] = None) -> str:
        """Вызов локальной модели через LM Studio API"""
        if not self._lm_studio_available:
            self._check_lm_studio()
        
        if not self._lm_studio_available:
            return "Ошибка: LM Studio не запущен или не доступен. Запустите LM Studio и загрузите модель DeepSeek."
        
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        payload = {
            "model": self.lm_studio_model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0.7,
            "stream": False
        }
        if response_format:
            payload["response_format"] = response_format
        
        try:
            response = requests.post(
                f"{self.lm_studio_url}/chat/completions",
                json=payload,
                timeout=120
            )
            
            if response.status_code == 200:
                return response.json()["choices"][0]["message"]["content"]
            else:
                _safe_print(f"LM Studio ошибка: {response.status_code} - {response.text}")
                return f"Ошибка LM Studio: {response.status_code}"
        except requests.exceptions.ConnectionError:
            return "Ошибка: LM Studio не запущен. Запустите LM Studio и включите Local Inference Server."
        except Exception as e:
            _safe_print(f"Ошибка вызова LM Studio: {e}")
            return f"Ошибка: {str(e)}"
    
    def _call_deepseek_api(self, prompt: str, system_prompt: Optional[str] = None,
                           max_tokens: int = 2000, response_format: Optional[Dict] = None) -> str:
        """Вызов облачного DeepSeek API (https://api.deepseek.com/chat/completions)"""
        if not self.api_key:
            return "Ошибка: API ключ DeepSeek не указан в .env файле"
        
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "reasoning_effort": self.reasoning_effort,
            "thinking": {"type": self.thinking}
        }
        if response_format:
            payload["response_format"] = response_format
        
        try:
            response = requests.post(
                f"{self.api_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=120
            )
            
            if response.status_code == 200:
                return response.json()["choices"][0]["message"]["content"]
            else:
                _safe_print(f"API ошибка: {response.status_code} - {response.text}")
                return f"Ошибка API: {response.status_code}"
        except Exception as e:
            _safe_print(f"Ошибка вызова API: {e}")
            return f"Ошибка: {str(e)}"
    
    def generate(self, prompt: str, system_prompt: Optional[str] = None,
                 max_tokens: int = 2000, response_format: Optional[Dict] = None) -> str:
        """Генерация текста через выбранный режим"""
        if self.mode == 'lm-studio':
            return self._call_lm_studio(prompt, system_prompt, max_tokens, response_format)
        else:
            return self._call_deepseek_api(prompt, system_prompt, max_tokens, response_format)
    
    def analyze_event(self, title: str, description: str, year: int) -> Dict:
        """Анализ исторического события с помощью DeepSeek"""
        
        system_prompt = """Ты — нейросеть С.А.Ф.О.Н., система анализа исторических событий. 
Твоя задача — классифицировать событие и определить его параметры.
Отвечай ТОЛЬКО в формате JSON, без лишнего текста.
Формат ответа:
{
    "category": "категория (война/экономический кризис/эпидемия/землетрясение/цунами/наводнение/пожар/революция/голод/ураган)",
    "magnitude": 0.0-1.0 (масштаб события, где 1.0 — катастрофа мирового уровня),
    "importance": 0.0-1.0 (важность для истории, долгосрочные последствия),
    "causes": ["причина1", "причина2"],
    "effects": ["следствие1", "следствие2"],
    "location": "вероятная локация (страна или регион)"
}"""
        
        prompt = f"""Проанализируй историческое событие:
Название: {title}
Описание: {description}
Год: {year}

Определи категорию, масштаб (0-1), важность (0-1), вероятные причины и следствия."""
        
        response = self.generate(prompt, system_prompt, max_tokens=1000,
                                 response_format={"type": "json_object"})
        
        # Парсим JSON из ответа
        try:
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
        except json.JSONDecodeError as e:
            _safe_print(f"JSON парсинг ошибка: {e}")
            _safe_print(f"Ответ: {response[:200]}")
        
        # fallback
        return {
            "category": "событие",
            "magnitude": 0.5,
            "importance": 0.5,
            "causes": ["не определено"],
            "effects": ["не определено"],
            "location": "глобально"
        }
    
    def generate_prediction_text(self, prediction: Dict, events_context: str = "",
                                   current_context: str = "") -> str:
        """Генерация глубинного причинно-следственного описания с контекстом"""

        system_prompt = """Ты — С.А.Ф.О.Н., аналитическая система прогнозирования на основе исторических циклов.
Твоя задача: написать ГЛУБОКИЙ, АНАЛИТИЧЕСКИЙ текст предсказания, раскрывающий причинно-следственную логику.

СТРУКТУРА ОТВЕТА (используй разделы, но БЕЗ нумерации — плавный связный текст):

[Исторический контекст]
Какие конкретные события прошлого формируют этот цикл. Назови их, укажи годы.
Объясни ПОЧЕМУ этот цикл существует: что связывает эти события?

[Текущая ситуация]
Что происходит СЕЙЧАС, что делает это предсказание актуальным?
Какие факторы уже указывают на приближение события?

[Прогноз]
Что, где и когда ожидается. Укажи масштаб: магнитуда, потери, охват.
Свяжи с последним событием цикла: "после X в году Y, через Z лет — ожидается..."

[Последствия]
Какие регионы/секторы наиболее уязвимы. Что может усилить/ослабить событие.

ТРЕБОВАНИЯ:
- Пиши на русском, живым аналитическим языком, 300-500 слов
- Используй КОНКРЕТНЫЕ цифры из предоставленных данных
- Строй причинно-следственную цепочку: прошлое → настоящее → будущее
- Указывай ВЕРОЯТНОСТЬ и ЧТО ОНА ЗНАЧИТ (высокая/средняя/низкая)
- Упоминай астрометрические факторы если они указаны в reasoning
- НЕ используй нумерацию разделов в финальном тексте — просто абзацы
- НЕ выдумывай факты, опирайся ТОЛЬКО на предоставленные данные"""

        reasoning = prediction.get('reasoning', '')
        category = prediction.get('category', '')
        year = prediction.get('year', '')
        location = prediction.get('location', '')
        probability = prediction.get('probability', 0.5) * 100

        prob_label = "критически высокая" if probability >= 85 else "высокая" if probability >= 70 else "повышенная" if probability >= 50 else "умеренная"

        prompt = f"""Сформируй аналитическое предсказание.

===== ДАННЫЕ ПРОГНОЗА =====
Категория: {category}
Прогнозируемый год: {year}
Вероятная локация: {location}
Вероятность: {probability:.0f}% ({prob_label})

===== ОБОСНОВАНИЕ ЦИКЛА =====
{reasoning}

===== ИСТОРИЧЕСКИЙ КОНТЕКСТ (события этого цикла) =====
{events_context if events_context else 'См. обоснование цикла выше.'}

===== ТЕКУЩАЯ СИТУАЦИЯ =====
{current_context if current_context else 'Анализ выполняется в ' + str(datetime.now().year) + ' году. Геополитическая и экономическая обстановка учитывается в вероятностной модели.'}

Напиши развёрнутый аналитический прогноз (300-500 слов)."""

        response = self.generate(prompt, system_prompt, max_tokens=800)

        if response.startswith('"') and response.endswith('"'):
            response = response[1:-1]

        return response
    
    def analyze_astrometry(self, year: int, planetary_data: Dict) -> Dict:
        """Анализ астрометрических данных с помощью DeepSeek"""
        
        system_prompt = """Ты — астрометрический аналитик С.А.Ф.О.Н.а.
Анализируй корреляции между планетарными положениями и историческими событиями.
Отвечай ТОЛЬКО в формате JSON с полями:
- "significance" (0-1): насколько значима эта конфигурация
- "explanation": краткое объяснение на русском
- "recommended_boost" (0.8-1.5): коэффициент повышения вероятности события"""
        
        prompt = f"""Проанализируй планетарную конфигурацию для {year} года:
{json.dumps(planetary_data, indent=2, ensure_ascii=False)}

Определи, насколько эта конфигурация коррелирует с историческими событиями."""
        
        response = self.generate(prompt, system_prompt, max_tokens=500)
        
        try:
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
        except Exception:
            pass
        
        return {"significance": 0.5, "explanation": "Анализ не выполнен", "recommended_boost": 1.0}

    def get_wikipedia_context(self, event_titles: list) -> str:
        """Получает краткие описания исторических событий из Wikipedia для контекста"""
        if not event_titles:
            return ""
        contexts = []
        for title in event_titles[:3]:
            try:
                url = "https://en.wikipedia.org/w/api.php"
                params = {
                    "action": "query", "prop": "extracts", "exintro": 1,
                    "explaintext": 1, "titles": title, "format": "json",
                }
                resp = requests.get(url, params=params, timeout=10)
                data = resp.json()
                pages = data.get("query", {}).get("pages", {})
                for page in pages.values():
                    extract = page.get("extract", "")
                    if extract:
                        contexts.append(f"{title}: {extract[:400]}")
            except Exception:
                pass
        return "\n\n".join(contexts)

    def get_current_context(self, category: str) -> str:
        """Возвращает контекст текущей ситуации для категории"""
        year = datetime.now().year
        template = get_current_contexts().get(category)
        if template:
            try:
                return template.format(year=year)
            except (KeyError, IndexError):
                return template
        return f"Анализ текущей обстановки {year} года."

    
    def get_system_status(self) -> Dict:
        """Статус нейросетевого движка"""
        status = {
            "mode": self.mode,
            "available": False,
            "model": "",
            "thinking": self.thinking,
            "reasoning_effort": self.reasoning_effort,
            "api_key_configured": False
        }
        
        if self.mode == 'lm-studio':
            status["model"] = self.lm_studio_model
            status["available"] = self._check_lm_studio() if self._lm_studio_available is None else self._lm_studio_available
        else:
            status["model"] = self.model
            status["api_key_configured"] = bool(self.api_key)
            status["available"] = bool(self.api_key)
        
        return status


# ==================== ФАБРИКА ДЛЯ ИСПОЛЬЗОВАНИЯ В ПРОЕКТЕ ====================

_deepseek_instance = None

def get_deepseek_engine(config: Optional[Dict] = None) -> DeepSeekEngine:
    """Singleton для получения экземпляра DeepSeek"""
    global _deepseek_instance
    if _deepseek_instance is None:
        if config is None:
            from dotenv import load_dotenv
            load_dotenv()
            config = {
                'DEEPSEEK_MODE': os.getenv('DEEPSEEK_MODE', 'lm-studio'),
                'DEEPSEEK_API_KEY': os.getenv('DEEPSEEK_API_KEY', ''),
                'DEEPSEEK_API_URL': os.getenv('DEEPSEEK_API_URL', 'https://api.deepseek.com'),
                'DEEPSEEK_MODEL': os.getenv('DEEPSEEK_MODEL', 'deepseek-flash'),
                'DEEPSEEK_THINKING': os.getenv('DEEPSEEK_THINKING', 'enabled'),
                'DEEPSEEK_REASONING_EFFORT': os.getenv('DEEPSEEK_REASONING_EFFORT', 'high'),
                'LM_STUDIO_URL': os.getenv('LM_STUDIO_URL', 'http://localhost:1234/v1'),
                'LM_STUDIO_MODEL': os.getenv('LM_STUDIO_MODEL', 'deepseek-v4-pro'),
            }
        _deepseek_instance = DeepSeekEngine(config)
    return _deepseek_instance