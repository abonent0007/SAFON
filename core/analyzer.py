"""
Модуль анализа событий с использованием DeepSeek V4 Pro
Поддерживает: облачный API и локальный LM Studio
"""

from typing import Dict
from .deepseek_engine import get_deepseek_engine

from dotenv import load_dotenv
load_dotenv()


def _safe_print(message):
    try:
        print(message)
    except UnicodeEncodeError:
        print(message.encode('ascii', errors='replace').decode('ascii'))


class UltimateSemanticAnalyzer:
    """Анализатор с использованием DeepSeek V4 Pro (LM Studio или API)"""
    
    def __init__(self):
        _safe_print("🧠 Инициализация нейросетевого анализатора DeepSeek V4 Pro...")
        self.deepseek = get_deepseek_engine()
        status = self.deepseek.get_system_status()
        
        if status['available']:
            if status['mode'] == 'lm-studio':
                _safe_print("   ✅ LM Studio обнаружен! DeepSeek V4 Pro готов (порт: 1234)")
            else:
                _safe_print(f"   ✅ DeepSeek API готов (модель: {status['model']})")
        else:
            _safe_print(f"   ⚠️ DeepSeek не доступен! Режим: {status['mode']}")
            if status['mode'] == 'lm-studio':
                _safe_print("   → Запустите LM Studio и нажмите 'Start Local Inference Server'")
            else:
                _safe_print("   → Проверьте DEEPSEEK_API_KEY в .env файле")
    
    def analyze(self, title: str, description: str, year: int, location: str = "") -> Dict:
        """
        Анализирует событие с помощью DeepSeek V4 Pro
        """
        try:
            result = self.deepseek.analyze_event(title, description, year)
            
            if not result.get('location') or result['location'] == 'не определено':
                result['location'] = location or self._extract_location_fallback(title + " " + description)
            
            result['causal_delay'] = self._get_causal_delay(result.get('category', 'событие'))
            result['analysis_confidence'] = result.get('importance', 0.7)
            
            return result
        except Exception as e:
            print(f"Ошибка анализа через DeepSeek: {e}")
            return self._fallback_analysis(title, description, year, location)
    
    def _fallback_analysis(self, title: str, description: str, year: int, location: str) -> Dict:
        """Упрощённый анализ без нейросети (на случай ошибки)"""
        text = (title + " " + description).lower()
        
        categories = {
            "война": ["войн", "конфликт", "вторжени", "битв"],
            "экономический кризис": ["кризис", "депресси", "обвал", "инфляц"],
            "землетрясение": ["землетряс", "сейсмич"],
            "цунами": ["цунам"],
            "наводнение": ["наводн", "паводк"],
            "пожар": ["пожар", "горел"],
        }
        
        for cat, keywords in categories.items():
            if any(kw in text for kw in keywords):
                return {
                    "category": cat,
                    "magnitude": 0.6,
                    "importance": 0.6,
                    "causes": ["не определено"],
                    "effects": ["не определено"],
                    "location": location or "глобально",
                    "causal_delay": self._get_causal_delay(cat),
                    "analysis_confidence": 0.5
                }
        
        return {
            "category": "событие",
            "magnitude": 0.5,
            "importance": 0.5,
            "causes": ["не определено"],
            "effects": ["не определено"],
            "location": location or "глобально",
            "causal_delay": 2,
            "analysis_confidence": 0.3
        }
    
    def _extract_location_fallback(self, text: str) -> str:
        locations = ["Европа", "Азия", "Африка", "Америка", "США", "Китай", 
                     "Индия", "Россия", "Япония", "Индонезия", "глобально"]
        text_lower = text.lower()
        for loc in locations:
            if loc.lower() in text_lower:
                return loc
        return "глобально"
    
    def _get_causal_delay(self, category: str) -> int:
        delays = {
            "экономический кризис": 1,
            "землетрясение": 0,
            "цунами": 0,
            "наводнение": 0,
            "пожар": 0,
            "война": 3,
            "эпидемия": 2,
            "революция": 2
        }
        return delays.get(category, 2)
    
    def enhance_prediction(self, prediction: Dict) -> Dict:
        """Улучшает предсказание с помощью DeepSeek"""
        if not self.deepseek.get_system_status()['available']:
            return prediction
        
        try:
            description = self.deepseek.generate_prediction_text(prediction)
            if description and "Ошибка" not in description and len(description) > 20:
                prediction['description'] = description
                prediction['ai_enhanced'] = True
        except Exception as e:
            print(f"Ошибка генерации описания: {e}")
        
        return prediction
    
    def get_status(self) -> Dict:
        """Возвращает статус анализатора"""
        return self.deepseek.get_system_status()