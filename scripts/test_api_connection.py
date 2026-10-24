# -*- coding: utf-8 -*-
"""Live smoke test: DeepSeek API connection + JSON mode.
Docs: base https://api.deepseek.com, POST /chat/completions, model deepseek-flash."""
import sys
import time

getattr(sys.stdout, "reconfigure")(encoding="utf-8")
sys.path.insert(0, r"C:\Users\User\Documents\SAFON")

from core.deepseek_engine import get_deepseek_engine  # noqa: E402

eng = get_deepseek_engine()
st = eng.get_system_status()
print("STATUS: mode=%s model=%s thinking=%s effort=%s" % (
    st["mode"], st["model"], st["thinking"], st["reasoning_effort"]))
print("ENDPOINT:", eng.api_url + "/chat/completions")

print("\n[TEST 1] plain generate...")
t0 = time.time()
out = eng.generate("Ответь ровно одним словом: работает", max_tokens=1500)
print("elapsed: %.1fs" % (time.time() - t0))
print("REPLY:", str(out).strip()[:200])

print("\n[TEST 2] analyze_event (response_format=json_object)...")
t0 = time.time()
res = eng.analyze_event("Тест соединения", "Проверка конфигурации API системы прогнозирования", 2026)
print("elapsed: %.1fs" % (time.time() - t0))
print("PARSED:", {k: res.get(k) for k in ("category", "magnitude", "importance", "location")})

ok1 = bool(out) and not str(out).startswith("Ошибка")
print("\nRESULT:", "CONNECTION OK" if ok1 else "TEST1 FAIL")
