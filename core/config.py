# -*- coding: utf-8 -*-
"""Центральный конфиг SAFON.

Все ранее захардкоженные данные вынесены в config/safon_config.json:
категории, локации, циклы, описания, сезонные месяцы, контексты, шаблоны обогащения.
Файл перечитывается автоматически при изменении (проверка mtime при каждом обращении)."""

import json
import os
import threading
from typing import Any, Dict

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_DIR = os.path.join(_ROOT, "config")
CONFIG_PATH = os.path.join(CONFIG_DIR, "safon_config.json")

_lock = threading.Lock()
_cache: Dict[str, Any] = {}
_mtime = None


def _load_file() -> Dict[str, Any]:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def get_config(force: bool = False) -> Dict[str, Any]:
    """Возвращает конфиг; при изменении файла на диске — перечитывает (авто-обновление)."""
    global _cache, _mtime
    try:
        mtime = os.path.getmtime(CONFIG_PATH)
    except OSError:
        mtime = None
    with _lock:
        if force or not _cache or (mtime is not None and mtime != _mtime):
            _cache = _load_file()
            _mtime = mtime
        return _cache


def get_categories() -> Dict[str, Dict]:
    return get_config().get("categories", {})


def get_locations() -> Dict[str, Dict]:
    return get_config().get("locations", {})


def get_cycles() -> Dict[str, Dict]:
    return get_config().get("cycles", {})


def get_descriptions() -> Dict[str, str]:
    return get_config().get("descriptions", {})


def get_seasonal_months() -> Dict[str, list]:
    return get_config().get("seasonal_months", {})


def get_current_contexts() -> Dict[str, str]:
    return get_config().get("current_contexts", {})


def get_enrichment_templates() -> Dict[str, Dict]:
    return get_config().get("enrichment", {})
