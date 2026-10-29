#!/usr/bin/env python3
"""Evaluate Sakhi's Gemini-backed decisions against labelled cases.

    python scripts/run_llm_eval.py            # run only if core logic changed since the last run
    python scripts/run_llm_eval.py --check    # never calls Gemini; warns if the stored results are stale
    python scripts/run_llm_eval.py --force    # run regardless (spends quota)

The unit, component and journey tests script Gemini's answers, so they prove
what the code does with an answer - not whether Gemini gives the right one.
This does: it sends every case in backend/evals/cases.json to the real model,
through the real routing and agent code, and scores the result.

It spends real quota (about 110 Gemini calls), so it runs once and is then
pinned to a fingerprint of everything that shapes the model's behaviour -
the prompts and routing code, the agents, the case file and the configured
model names (never the API keys). Until one of those changes, a plain run
prints the stored results instead of calling Gemini, and CI only runs
--check, which never calls it.

Gemini runs for real; everything else is the test fakes: the in-memory
catalog and database from backend/tests/support, and a word-based search in
place of embeddings, so a case measures the decision, not the retrieval.
"""
import argparse
import hashlib
import json
import logging
import os
import re
import sys
import time
from pathlib import Path
from statistics import fmean

ROOT = Path(__file__).resolve().parent.parent
CASES = ROOT / "backend" / "evals" / "cases.json"
RESULTS = ROOT / "backend" / "evals" / "results.json"
REPORT = ROOT / "backend" / "evals" / "RESULTS.md"

# Everything whose change can change what the model is asked or how its
# answer is used.
FINGERPRINTED = [
    "backend/core/routing", "backend/core/agents", "backend/core/orchestrator.py",
    "backend/core/gemini_utils.py", "backend/core/prompt_safety.py", "backend/core/pricing.py",
    "backend/core/constants.py", "backend/core/rag/formatting.py", "backend/core/catalog/captions.py",
    "backend/evals/cases.json", "scripts/run_llm_eval.py",
]
PAUSE_SECONDS = 4.0  # stays under the free tier's requests-per-minute


def fingerprint() -> str:
    sys.path.insert(0, str(ROOT))
    from backend.config import settings

    digest = hashlib.sha256()
    for entry in FINGERPRINTED:
        path = ROOT / entry
        files = sorted(path.rglob("*.py")) if path.is_dir() else [path]
        for file in files:
            digest.update(str(file.relative_to(ROOT)).encode())
            digest.update(file.read_bytes())
    digest.update(f"{settings.GEMINI_MODEL}|{settings.GEMINI_FALLBACK_MODELS}".encode())
    return digest.hexdigest()[:16]


def percentile(values, q):
    ordered = sorted(values)
    return ordered[max(1, -(-q * len(ordered) // 100)) - 1]


# ── running the cases ───────────────────────────────────────────────

class _ModelLog(logging.Handler):
    """Notes which model actually answered each call (the fallback chain may
    move past the primary on quota errors), from gemini_utils' own log lines."""

    def __init__(self):
        super().__init__()
        self.models = []

    def emit(self, record):
        match = re.search(r"success using model '([^']+)'", record.getMessage())
        if match:
            self.models.append(match.group(1))


def run_cases(cases: dict) -> dict:
    os.environ["SESSION_STORE"] = "memory"
    os.environ.setdefault("ENVIRONMENT", "development")
    sys.path.insert(0, str(ROOT))

    from backend.core import gemini_utils, session
    from backend.core.agents.customer import run_customer_agent
    from backend.core.orchestrator import detect_intent
    from backend.core.routing.approval import classify_approval_intent
    from backend.core.routing.attribute_followup import classify_attribute_followup
    from backend.core.routing.buying_interest import classify_buying_interest
    from backend.core.routing.category import extract_category_intent
    from backend.core.routing.exchange import classify_exchange_confirmation
    from backend.core.routing.returns import classify_return_grievance
    from backend.core.state import _pending_key
    from backend.db.supabase_client import db_client
    from backend.tests.support.catalog import CATALOG
    from backend.tests.support.fakes import FakeSupabase, fake_embedding
    from backend.tests.support.harness import Sakhi, _replace_everywhere
    from backend.tests.support.sessions import SESSION_A

    if not gemini_utils._get_gemini_keys():
        sys.exit("No Gemini API key configured (GEMINI_API_KEY in .env); nothing to evaluate against.")

    class Patches:
        def __init__(self):
            self.undo = []

        def setattr(self, target, name, value):
            self.undo.append((target, name, getattr(target, name)))
            setattr(target, name, value)

        def restore(self):
            for target, name, value in reversed(self.undo):
                setattr(target, name, value)

    patches = Patches()
    model_log = _ModelLog()
    logging.getLogger("sakhi-backend").addHandler(model_log)
    logging.getLogger("sakhi-backend").setLevel(logging.INFO)

    def fresh_world():
        db = FakeSupabase(CATALOG)
        for method in FakeSupabase.METHODS:
            patches.setattr(db_client, method, getattr(db, method))
        patches.setattr(session, "store", session.InMemorySessionStore())
        return Sakhi(gemini=None, classifiers=None, db=db)

    _replace_everywhere(patches, gemini_utils.embed_content_with_fallback, fake_embedding)

    draft = {"matched_product_name": "Red Banarasi Silk Saree", "selling_price": 599}
    deciders = {
        "intent": lambda c, w: detect_intent(w.state(c["text"], mode=c["mode"]))["detected_intent"],
        "approval": lambda c, w: classify_approval_intent(c["text"], draft),
        "grievance": lambda c, w: classify_return_grievance(c["text"], "Pink Cotton Kurti"),
        "exchange": lambda c, w: classify_exchange_confirmation(c["text"]),
        "category": lambda c, w: extract_category_intent(c["text"], c["current"]),
        "attribute_followup": lambda c, w: classify_attribute_followup(c["text"], "Pink Cotton Kurti"),
        "buying_interest": lambda c, w: classify_buying_interest(c["text"], "Green Anarkali Suit"),
    }

    results = {}
    try:
        for suite, suite_cases in cases.items():
            rows = []
            for case in suite_cases:
                world = fresh_world()
                calls_before = len(model_log.models)
                started = time.perf_counter()
                if suite == "customer_agent":
                    if case.get("on_screen"):
                        session.LAST_VIEWED_PRODUCT[_pending_key(SESSION_A, "customer")] = world.db.products[case["on_screen"]]
                    state = run_customer_agent(world.state(case["text"]))
                    got, passed = _judge_customer_turn(case["expect"], state, world.db)
                else:
                    got = deciders[suite](case, world)
                    allowed = case["expect"] if isinstance(case["expect"], list) else [case["expect"]]
                    passed = got in allowed
                elapsed_ms = round((time.perf_counter() - started) * 1000)
                rows.append({
                    "case": case.get("id") or case["text"], "tag": case.get("tag"), "expected": case["expect"],
                    "got": got, "passed": passed, "ms": elapsed_ms,
                    "models": model_log.models[calls_before:],
                })
                mark = "ok " if passed else "XX "
                print(f"  {mark}{suite:<18} {elapsed_ms:>6} ms  {rows[-1]['case'][:60]}", flush=True)
                time.sleep(PAUSE_SECONDS)
            results[suite] = rows
    finally:
        patches.restore()
    return results


def _judge_customer_turn(expect: dict, state: dict, db) -> tuple:
    """Scores one customer-agent turn on what a buyer would actually get:
    a photo means it answered from the catalog, an order row means it
    ordered, a seeded return means the returns funnel will take the next
    message, and the prices in the reply are the prices the buyer was told."""
    from backend.core.pricing import mentioned_prices
    from backend.core.session import PENDING_RETURNS
    from backend.core.state import _pending_key

    stated = mentioned_prices(state["reply_text"] or "") + mentioned_prices(state["reply_tts_text"] or "")
    order_for = db.orders[0]["product_id"] if db.orders else None
    observed = {
        "answered_from_product_context": state["reply_image_url"] is not None,
        "purchase_intent_detected": bool(state["reply_purchase_intent_detected"]),
        "return_retention_triggered": _pending_key(state["session_id"], "customer") in PENDING_RETURNS,
    }

    checks = []
    for key, wanted in expect.items():
        if key in observed:
            checks.append(observed[key] == wanted)
        elif key == "states_price":
            checks.append(wanted in stated)
        elif key == "never_states_price":
            checks.append(wanted not in stated)
        elif key == "mentions":
            checks.append(wanted.lower() in (state["reply_text"] or "").lower())
        elif key == "order_for":
            checks.append(order_for == wanted)
        else:
            raise ValueError(f"unknown expectation {key!r}")
    return {"reply": state["reply_text"], "stated_prices": stated, "order_for": order_for, **observed}, all(checks)


# ── reporting ───────────────────────────────────────────────────────

def summarize(results: dict) -> dict:
    summary = {}
    for suite, rows in results.items():
        times = [r["ms"] for r in rows]
        summary[suite] = {
            "cases": len(rows), "passed": sum(r["passed"] for r in rows),
            "accuracy": round(sum(r["passed"] for r in rows) / len(rows), 3),
            "p50_ms": percentile(times, 50), "p95_ms": percentile(times, 95), "mean_ms": round(fmean(times)),
        }
    all_rows = [r for rows in results.values() for r in rows]
    injection = [r for r in all_rows if r["tag"] == "injection"]
    summary["_overall"] = {
        "cases": len(all_rows), "passed": sum(r["passed"] for r in all_rows),
        "accuracy": round(sum(r["passed"] for r in all_rows) / len(all_rows), 3),
        "injection_cases_held": f"{sum(r['passed'] for r in injection)}/{len(injection)}",
    }
    return summary


def write_report(payload: dict) -> None:
    s = payload["summary"]
    lines = [
        "# LLM evaluation results",
        "",
        f"Run on {payload['ran_at']} against `{payload['primary_model']}` (fallbacks: {payload['fallback_models']}).",
        f"Fingerprint `{payload['fingerprint']}` - re-run only when core logic changes "
        "(`python scripts/run_llm_eval.py`). Generated by the script; do not edit by hand.",
        "",
        f"**Overall: {s['_overall']['passed']}/{s['_overall']['cases']} "
        f"({s['_overall']['accuracy']:.0%}); injection attempts held: {s['_overall']['injection_cases_held']}.**",
        "",
        "| Decision | Cases | Correct | Accuracy | p50 ms | p95 ms |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for suite, row in s.items():
        if suite.startswith("_"):
            continue
        lines.append(f"| {suite} | {row['cases']} | {row['passed']} | {row['accuracy']:.0%} | {row['p50_ms']} | {row['p95_ms']} |")
    lines += ["", "Latency is wall time per case from this machine, including the network and any fallback",
              "to another model; a customer-agent case is several Gemini calls.", "", "## Misses", ""]
    misses = [(suite, r) for suite, rows in payload["results"].items() for r in rows if not r["passed"]]
    if not misses:
        lines.append("None.")
    for suite, r in misses:
        lines.append(f"- **{suite}** - `{r['case']}`: expected `{json.dumps(r['expected'], ensure_ascii=False)}`, "
                     f"got `{json.dumps(r['got'], ensure_ascii=False)}`")
    REPORT.write_text("\n".join(lines) + "\n")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate Gemini-backed decisions against labelled cases.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--check", action="store_true", help="never call Gemini; warn if the results are stale")
    group.add_argument("--force", action="store_true", help="run even if nothing changed (spends quota)")
    args = parser.parse_args(argv)

    current = fingerprint()
    stored = json.loads(RESULTS.read_text()) if RESULTS.exists() else None
    fresh = stored is not None and stored["fingerprint"] == current

    if args.check:
        if fresh:
            print(f"LLM eval results are current (fingerprint {current}).")
        else:
            # A GitHub Actions annotation; a warning, not a failure, so CI never spends quota.
            print(f"::warning title=LLM eval is stale::Core logic changed since the last evaluation "
                  f"(stored {stored['fingerprint'] if stored else 'none'}, now {current}). "
                  f"Run `python scripts/run_llm_eval.py` once.")
        return 0

    if fresh and not args.force:
        print(f"Nothing changed since the last run (fingerprint {current}); not calling Gemini.")
        print(REPORT.read_text())
        return 0

    from backend.config import settings
    print(f"Evaluating against Gemini ({settings.GEMINI_MODEL}); this spends quota.", flush=True)
    results = run_cases(json.loads(CASES.read_text()))
    payload = {
        "fingerprint": current,
        "ran_at": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()),
        "primary_model": settings.GEMINI_MODEL,
        "fallback_models": settings.GEMINI_FALLBACK_MODELS,
        "summary": summarize(results),
        "results": results,
    }
    RESULTS.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    write_report(payload)
    print(REPORT.read_text())
    return 0


if __name__ == "__main__":
    sys.exit(main())
