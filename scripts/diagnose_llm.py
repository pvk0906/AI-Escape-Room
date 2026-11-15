"""Quick check of the configured LLM: each call has a hard time limit.

Run:  python scripts/diagnose_llm.py
"""
import sys, time, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from common.llm import LLMClient, Message

c = LLMClient.from_env()
c.timeout, c.max_retries = 25.0, 1
print("Using:", c.description)
tests = [
    ("plain", dict()),
    ("json_mode", dict(json_mode=True, max_tokens=200, temperature=0.0)),
    ("narrator-style", dict(max_tokens=220, temperature=0.7)),
]
for name, kw in tests:
    t = time.time()
    try:
        out = c.generate('Reply with JSON {"ok": true}' if "json" in name else "Be terse.",
                         [Message("user", "go" if "json" in name else "Say OK")], **kw)
        print(f"{name:15} OK  {time.time()-t:5.1f}s  {out[:60]!r}")
    except Exception as e:  # noqa: BLE001
        print(f"{name:15} FAIL {time.time()-t:5.1f}s  {str(e)[:200]}")
