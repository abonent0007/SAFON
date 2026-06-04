"""
Модуль интеграции с DeepSeek V4 Pro
Поддерживает:
- API DeepSeek (облачный)
- Локальный запуск через LM Studio (http://localhost:1234/v1)
"""

import os
import re
import json
import requests
from typing import Dict


def _safe_print(message):
    try:
        print(message)
    except UnicodeEncodeError:
        print(message.encode('ascii', errors='replace').decode('ascii'))


class DeepSeekEngine:
    """Интеграция с DeepSeek V4 Pro через API (облачный или LM Studio)"""
    
    def __init__(self, config: Dict):
        self.mode = config.get('DEEPSEEK_MODE', 'lm-studio')
        
        # API DeepSeek (облачный)
        self.api_key = config.get('DEEPSEEK_API_KEY', '')
        self.api_url = config.get('DEEPSEEK_API_URL', 'https://api.deepseek.com/v1')
        self.model = config.get('DEEPSEEK_MODEL', 'deepseek-chat')
        
        # LM Studio (локальный)
        self.lm_studio_url = config.get('LM_STUDIO_URL', 'http://localhost:1234/v1')
        self.lm_studio_model = config.get('LM_STUDIO_MODEL', 'deepseek-v4-pro')
        
        self._lm_studio_available = None
        
        _safe_print(f"🤖 DeepSeek V4 Pro инициализация (режим: {self.mode})")
        
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
    
    def _call_lm_studio(self, prompt: str, system_prompt: str = None, max_tokens: int = 2000) -> str:
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
        
        try:
            response = requests.post(
                f"{self.lm_studio_url}/chat/completions",
                json=payload,
                timeout=120
            )
            
            if response.status_code == 200:
                return response.json()["choices"][0]["message"]["content"]
            else:
                print(f"LM Studio ошибка: {response.status_code} - {response.text}")
                return f"Ошибка LM Studio: {response.status_code}"
        except requests.exceptions.ConnectionError:
            return "Ошибка: LM Studio не запущен. Запустите LM Studio и включите Local Inference Server."
        except Exception as e:
            print(f"Ошибка вызова LM Studio: {e}")
            return f"Ошибка: {str(e)}"
    
    def _call_deepseek_api(self, prompt: str, system_prompt: str = None, max_tokens: int = 2000) -> str:
        """Вызов облачного DeepSeek API"""
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
            "temperature": 0.7
        }
        
        try:
            response = requests.post(
                f"{self.api_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=60
            )
            
            if response.status_code == 200:
                return response.json()["choices"][0]["message"]["content"]
            else:
                print(f"API ошибка: {response.status_code} - {response.text}")
                return f"Ошибка API: {response.status_code}"
        except Exception as e:
            print(f"Ошибка вызова API: {e}")
            return f"Ошибка: {str(e)}"
    
    def generate(self, prompt: str, system_prompt: str = None, max_tokens: int = 2000) -> str:
        """Генерация текста через выбранный режим"""
        if self.mode == 'lm-studio':
            return self._call_lm_studio(prompt, system_prompt, max_tokens)
        else:
            return self._call_deepseek_api(prompt, system_prompt, max_tokens)
    
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
        
        response = self.generate(prompt, system_prompt, max_tokens=1000)
        
        # Парсим JSON из ответа
        try:
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
        except json.JSONDecodeError as e:
            print(f"JSON парсинг ошибка: {e}")
            print(f"Ответ: {response[:200]}")
        
        # fallback
        return {
            "category": "событие",
            "magnitude": 0.5,
            "importance": 0.5,
            "causes": ["не определено"],
            "effects": ["не определено"],
            "location": "глобально"
        }
    
    def generate_prediction_text(self, prediction: Dict) -> str:
        """Генерация развёрнутого причинно-следственного описания предсказания"""

        system_prompt = """Ты — С.А.Ф.О.Н., система прогнозирования будущих событий на основе исторических циклов.
Твоя задача: создать РАЗВЁРНУТОЕ описание предсказания (4-6 предложений, не коротко!).

СТРУКТУРА ОТВЕТА (строго придерживайся):
1. Что именно прогнозируется (категория, вероятный масштаб)
2. Почему именно этот год (исторический цикл, повторяемость)
3. Какие исторические аналоги подтверждают прогноз
4. Вероятные последствия и уязвимые регионы

ТРЕБОВАНИЯ:
- Пиши на русском языке, развёрнуто, информативно
- Используй конкретные цифры из предоставленных данных
- Указывай причинно-следственную связь: какое прошлое событие → через какой цикл → это предсказание
- НЕ используй нумерацию, НЕ пиши "прогноз:", просто связный текст
- НЕ выдумывай факты, опирайся только на предоставленные данные"""

        reasoning = prediction.get('reasoning', '')
        description = prediction.get('description', '')
        category = prediction.get('category', '')
        year = prediction.get('year', '')
        location = prediction.get('location', '')
        probability = prediction.get('probability', 0.5) * 100

        prompt = f"""Сформируй развёрнутое описание предсказания:

КАТЕГОРИЯ: {category}
ГОД: {year}
ЛОКАЦИЯ: {location}
ВЕРОЯТНОСТЬ: {probability:.0f}%

ОБОСНОВАНИЕ ЦИКЛА: {reasoning}
БАЗОВОЕ ОПИСАНИЕ: {description}

Напиши развёрнутый анализ (4-6 предложений) этого будущего события с причинно-следственной связью."""

        response = self.generate(prompt, system_prompt, max_tokens=600)

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
    
    def get_system_status(self) -> Dict:
        """Статус нейросетевого движка"""
        status = {
            "mode": self.mode,
            "available": False,
            "model": "",
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

def get_deepseek_engine(config: Dict = None) -> DeepSeekEngine:
    """Singleton для получения экземпляра DeepSeek"""
    global _deepseek_instance
    if _deepseek_instance is None:
        if config is None:
            from dotenv import load_dotenv
            load_dotenv()
            config = {
                'DEEPSEEK_MODE': os.getenv('DEEPSEEK_MODE', 'lm-studio'),
                'DEEPSEEK_API_KEY': os.getenv('DEEPSEEK_API_KEY', ''),
                'DEEPSEEK_API_URL': os.getenv('DEEPSEEK_API_URL', 'https://api.deepseek.com/v1'),
                'DEEPSEEK_MODEL': os.getenv('DEEPSEEK_MODEL', 'deepseek-chat'),
                'LM_STUDIO_URL': os.getenv('LM_STUDIO_URL', 'http://localhost:1234/v1'),
                'LM_STUDIO_MODEL': os.getenv('LM_STUDIO_MODEL', 'deepseek-v4-pro'),
            }
        _deepseek_instance = DeepSeekEngine(config)
    return _deepseek_instance