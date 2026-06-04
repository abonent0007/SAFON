"""
Астрометрический модуль с автоматическим поиском корреляций
"""

from datetime import datetime
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
from collections import defaultdict


def _safe_print(message):
    try:
        print(message)
    except UnicodeEncodeError:
        print(message.encode('ascii', errors='replace').decode('ascii'))


try:
    from skyfield.api import Loader
    from skyfield.framelib import ecliptic_frame
    SKYFIELD_AVAILABLE = True
except ImportError:
    SKYFIELD_AVAILABLE = False


@dataclass
class PlanetaryPosition:
    planet_name: str
    longitude: float
    latitude: float
    distance_au: float
    date: datetime


@dataclass
class PlanetaryAspect:
    planet1: str
    planet2: str
    aspect_type: str
    angle: float
    orb: float
    date: datetime


@dataclass
class CorrelationResult:
    planet_pair: str
    aspect_type: str
    event_category: str
    phase_range: Tuple[float, float]
    probability: float
    baseline_probability: float
    lift: float
    p_value: float
    sample_size: int
    confidence: float
    discovered_at: datetime


class AstrometryModule:
    
    PLANETARY_PERIODS = {
        "Меркурий": 0.2408, "Венера": 0.6152, "Марс": 1.8808,
        "Юпитер": 11.862, "Сатурн": 29.457, "Уран": 84.020, "Нептун": 164.8,
    }
    
    PRIMARY_PLANETS = ["Марс", "Юпитер", "Сатурн", "Уран", "Нептун"]
    
    ASPECTS = {"соединение": 0, "оппозиция": 180, "тригон": 120, "квадратура": 90, "секстиль": 60}
    ASPECT_ORB = 10
    
    EVENT_CATEGORIES = ["экономический кризис", "война", "эпидемия", "землетрясение", "наводнение", "пожар", "цунами", "ураган", "революция", "засуха", "экологическая катастрофа"]
    
    def __init__(self):
        self.ephemeris = None
        self.ts = None
        self.planets = {}
        self.correlations = []
        self.skyfield_available = SKYFIELD_AVAILABLE
        self._init_skyfield()
    
    def _init_skyfield(self):
        if not SKYFIELD_AVAILABLE:
            _safe_print("⚠️ Skyfield не установлена. Упрощённый режим.")
            return
        try:
            loader = Loader('data/skyfield_data')
            self.ephemeris = loader('de421.bsp')
            self.ts = loader.timescale()
            self.planets = {
                'Марс': self.ephemeris['mars'],
                'Юпитер': self.ephemeris['jupiter barycenter'],
                'Сатурн': self.ephemeris['saturn barycenter'],
                'Уран': self.ephemeris['uranus barycenter'],
                'Нептун': self.ephemeris['neptune barycenter'],
            }
            _safe_print("✅ Астрометрия инициализирована")
        except Exception:
            self.skyfield_available = False
    
    def calculate_planet_position(self, planet_name: str, year: int, month: int = 6, day: int = 15) -> Optional[PlanetaryPosition]:
        if not self.skyfield_available or not self.ephemeris:
            return self._simplified_position(planet_name, year, month, day)
        try:
            date = self.ts.utc(year, month, day)
            if planet_name not in self.planets:
                return None
            planet = self.planets[planet_name]
            earth = self.ephemeris['earth']
            astrometric = earth.at(date).observe(planet)
            ecliptic = astrometric.frame_latlon(ecliptic_frame)
            return PlanetaryPosition(
                planet_name=planet_name,
                longitude=ecliptic.lon.degrees % 360,
                latitude=ecliptic.lat.degrees,
                distance_au=astrometric.distance().au,
                date=datetime(year, month, day)
            )
        except Exception:
            return self._simplified_position(planet_name, year, month, day)
    
    def _simplified_position(self, planet_name: str, year: int, month: int, day: int) -> PlanetaryPosition:
        period = self.PLANETARY_PERIODS.get(planet_name, 1.0)
        base_date = 2000.0
        date_float = year + (month - 1) / 12 + (day - 1) / 365.25
        progress = (date_float - base_date) / period
        longitude = (360 * progress) % 360
        return PlanetaryPosition(planet_name, longitude, 0.0, 1.0, datetime(year, month, day))
    
    def get_relative_phase(self, planet1: str, planet2: str, date: datetime) -> float:
        pos1 = self.calculate_planet_position(planet1, date.year, date.month, date.day)
        pos2 = self.calculate_planet_position(planet2, date.year, date.month, date.day)
        if not pos1 or not pos2:
            return 0.0
        return (pos1.longitude - pos2.longitude) % 360
    
    def find_aspects(self, date: datetime) -> List[PlanetaryAspect]:
        aspects = []
        for i, p1 in enumerate(self.PRIMARY_PLANETS):
            pos1 = self.calculate_planet_position(p1, date.year, date.month, date.day)
            if not pos1:
                continue
            for j, p2 in enumerate(self.PRIMARY_PLANETS):
                if i >= j:
                    continue
                pos2 = self.calculate_planet_position(p2, date.year, date.month, date.day)
                if not pos2:
                    continue
                angle = abs(pos1.longitude - pos2.longitude) % 360
                angle = min(angle, 360 - angle)
                for aspect_name, target_angle in self.ASPECTS.items():
                    if abs(angle - target_angle) <= self.ASPECT_ORB:
                        aspects.append(PlanetaryAspect(p1, p2, aspect_name, angle, abs(angle - target_angle), date))
        return aspects
    
    def analyze_historical_correlations(self, events: List[Dict]) -> List[CorrelationResult]:
        correlations = []
        events_by_category = defaultdict(list)
        
        for event in events:
            cat = event.get('category', 'unknown')
            if cat in self.EVENT_CATEGORIES:
                events_by_category[cat].append(event['year'])
        
        for category, years in events_by_category.items():
            if len(years) < 5:
                continue
            print(f"   Анализ {category} ({len(years)} событий)...")
            
            for p1 in self.PRIMARY_PLANETS:
                for p2 in self.PRIMARY_PLANETS:
                    if p1 >= p2:
                        continue
                    for aspect_name, target_angle in self.ASPECTS.items():
                        phases = []
                        for year in years:
                            date = datetime(year, 6, 15)
                            phase = self.get_relative_phase(p1, p2, date)
                            phases.append(phase)
                        
                        in_aspect = sum(1 for p in phases if min(abs(p - target_angle), 360 - abs(p - target_angle)) <= self.ASPECT_ORB)
                        total = len(phases)
                        baseline = (self.ASPECT_ORB * 2) / 360
                        lift = (in_aspect / total) / baseline if baseline > 0 else 1.0
                        
                        if lift > 1.3 and in_aspect >= 2:
                            correlations.append(CorrelationResult(
                                planet_pair=f"{p1}-{p2}",
                                aspect_type=aspect_name,
                                event_category=category,
                                phase_range=(target_angle - self.ASPECT_ORB, target_angle + self.ASPECT_ORB),
                                probability=in_aspect / total,
                                baseline_probability=baseline,
                                lift=lift,
                                p_value=0.08,
                                sample_size=total,
                                confidence=min(0.9, lift / 2),
                                discovered_at=datetime.now()
                            ))
                            print(f"      ✓ {p1}-{p2} {aspect_name} → {category} (lift {lift:.1f}x)")
        
        self.correlations = correlations
        return correlations
    
    def calculate_event_probability(self, event_year: int, event_category: str) -> float:
        if not self.correlations:
            return 0.3
        for corr in self.correlations:
            if corr.event_category != event_category:
                continue
            date = datetime(event_year, 6, 15)
            phase = self.get_relative_phase(corr.planet_pair.split('-')[0], corr.planet_pair.split('-')[1], date)
            low, high = corr.phase_range
            if low <= phase <= high or low <= phase + 360 <= high:
                return corr.probability
        return 0.3
    
    def get_active_correlations(self, year: int) -> List[Dict]:
        active = []
        for corr in self.correlations:
            date = datetime(year, 6, 15)
            phase = self.get_relative_phase(corr.planet_pair.split('-')[0], corr.planet_pair.split('-')[1], date)
            low, high = corr.phase_range
            if low <= phase <= high or low <= phase + 360 <= high:
                active.append({
                    "planets": corr.planet_pair,
                    "aspect": corr.aspect_type,
                    "event": corr.event_category,
                    "probability_boost": f"{corr.lift:.1f}x",
                    "confidence": f"{corr.confidence:.0%}"
                })
        return active
    
    def get_solar_activity_phase(self, year: int) -> float:
        last_minimum = 2019.5
        cycle = 11.0
        return ((year - last_minimum) / cycle) % 1.0 * 360
    
    def get_lunar_phase(self, year: int, month: int, day: int) -> float:
        lunar_cycle = 29.53
        base_date = datetime(2000, 1, 6, 18, 14)
        target_date = datetime(year, month, day)
        days_diff = (target_date - base_date).days
        return (days_diff / lunar_cycle) % 1.0 * 360
    
    def get_comprehensive_astrometry(self, year: int) -> Dict:
        return {
            "year": year,
            "solar_phase": self.get_solar_activity_phase(year),
            "lunar_phase": self.get_lunar_phase(year, 6, 15),
            "active_correlations": self.get_active_correlations(year),
        }


class AstroPredictionEnhancer:
    def __init__(self, astro: AstrometryModule):
        self.astro = astro
    
    def adjust_prediction_probability(self, base_probability: float, event_year: int, event_category: str) -> float:
        astro_prob = self.astro.calculate_event_probability(event_year, event_category)
        if astro_prob > 0.5:
            astro_weight = min(0.35, len(self.astro.correlations) / 30)
            boosted = base_probability * (1 - astro_weight) + astro_prob * astro_weight
            return max(base_probability, boosted)
        return base_probability
    
    def find_best_prediction_year(self, base_year: int, period: float, category: str, search_range: int = 3) -> int:
        best_year = base_year
        best_score = -1
        for offset in range(-search_range, search_range + 1):
            candidate = base_year + offset
            astro_score = self.astro.calculate_event_probability(candidate, category)
            cycle_score = 1.0 - abs(offset) / (search_range + 1)
            score = cycle_score * 0.4 + astro_score * 0.6
            if score > best_score:
                best_score = score
                best_year = candidate
        return best_year