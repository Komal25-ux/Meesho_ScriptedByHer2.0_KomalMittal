#!/usr/bin/env python3
"""How long Sakhi takes to answer, stage by stage, against a running backend.

    python scripts/measure_latency.py https://sakhi-backend-cbmz.onrender.com
    python scripts/measure_latency.py http://localhost:8000 --runs 3 --out latency.json

Each run sends the same ten typed messages from a fresh session (reseller
and customer side) and reads the Server-Timing header on every reply:
graph (agents + Gemini + Supabase), tts (Sarvam) and total, plus the wall
time seen by this script, which adds the network. Voice notes are not sent,
so speech-to-text is not measured here.

It spends real quota - about ten Gemini-backed turns and ten TTS calls per
run - and paces itself under the backend's per-session rate limit. The
first request wakes a sleeping Render instance; it is reported separately
as the cold start and left out of the percentiles.
"""
import argparse
import json
import math
import re
import statistics
import sys
import time
import uuid
from typing import Dict, List

MESSAGES = [
    ("reseller", "namaste didi"),
    ("reseller", "laal saree dikhao"),
    ("reseller", "pichle 7 din ki sales kaisi rahi?"),
    ("reseller", "kurti list karni hai"),
    ("reseller", "aur dikhao"),
    ("customer", "namaste"),
    ("customer", "koi cotton kurti hai?"),
    ("customer", "kitne ki hai?"),
    ("customer", "size kya kya hai?"),
    ("customer", "delivery kitne din mein hogi?"),
]
PAUSE_SECONDS = 3.5  # 10 messages a run stays under 20 per session per minute


def parse_server_timing(header: str) -> Dict[str, float]:
    """"graph;dur=2431, tts;dur=903" -> {"graph": 2431.0, "tts": 903.0}"""
    stages = {}
    for part in (header or "").split(","):
        match = re.match(r"\s*([\w-]+)\s*;\s*dur=([\d.]+)", part)
        if match:
            stages[match.group(1)] = float(match.group(2))
    return stages


def percentile(values: List[float], q: float) -> float:
    """Nearest-rank percentile: the smallest value with at least q% of the
    samples at or below it. With 20 samples, p95 is the 19th smallest."""
    if not values:
        raise ValueError("no samples")
    ordered = sorted(values)
    rank = max(1, math.ceil(q / 100 * len(ordered)))
    return ordered[rank - 1]


def summarize(samples: List[Dict[str, float]]) -> Dict[str, Dict[str, float]]:
    stages = sorted({name for sample in samples for name in sample})
    summary = {}
    for name in stages:
        values = [s[name] for s in samples if name in s]
        summary[name] = {
            "n": len(values),
            "p50": percentile(values, 50),
            "p95": percentile(values, 95),
            "max": max(values),
            "mean": round(statistics.fmean(values), 1),
        }
    return summary


def run(base_url: str, runs: int) -> dict:
    import httpx

    with httpx.Client(base_url=base_url, timeout=120) as client:
        started = time.perf_counter()
        client.get("/health").raise_for_status()
        cold_start_ms = (time.perf_counter() - started) * 1000

        samples = []
        for _ in range(runs):
            session = str(uuid.uuid4())
            for mode, text in MESSAGES:
                started = time.perf_counter()
                reply = client.post("/api/v1/chat/send", data={
                    "session_id": session, "text_message": text, "active_mode": mode,
                    "client_message_id": str(uuid.uuid4()),
                })
                wall_ms = (time.perf_counter() - started) * 1000
                reply.raise_for_status()
                sample = parse_server_timing(reply.headers.get("server-timing", ""))
                sample["wall"] = wall_ms
                samples.append(sample)
                time.sleep(PAUSE_SECONDS)
    return {"base_url": base_url, "cold_start_health_ms": round(cold_start_ms), "summary": summarize(samples)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("base_url")
    parser.add_argument("--runs", type=int, default=2)
    parser.add_argument("--out", help="also write the result as JSON to this file")
    args = parser.parse_args(argv)

    result = run(args.base_url.rstrip("/"), args.runs)
    print(f"cold start (first /health): {result['cold_start_health_ms']} ms")
    print(f"{'stage':<8}{'n':>4}{'p50 ms':>9}{'p95 ms':>9}{'max ms':>9}")
    for name, s in result["summary"].items():
        print(f"{name:<8}{s['n']:>4}{s['p50']:>9.0f}{s['p95']:>9.0f}{s['max']:>9.0f}")
    if args.out:
        with open(args.out, "w") as f:
            json.dump(result, f, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
