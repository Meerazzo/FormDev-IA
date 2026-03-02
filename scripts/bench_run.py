#!/usr/bin/env python3
import argparse
import json
import os
import statistics
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import urllib.request

# --- added (GPU monitor) ---
import subprocess
import threading
from shutil import which
# --------------------------

DEFAULT_API_URL = os.getenv("API_URL", "http://localhost:8080/v1/chat")
DEFAULT_API_KEY = os.getenv("API_KEY", "")
DEFAULT_MODEL = os.getenv("MODEL_ID", "")  # optionnel: peut rester vide si vLLM ignore/override


def _now_tag() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _percentile(values: List[float], p: float) -> float:
    if not values:
        return float("nan")
    s = sorted(values)
    k = (len(s) - 1) * p
    f = int(k)
    c = min(f + 1, len(s) - 1)
    if f == c:
        return s[f]
    return s[f] + (s[c] - s[f]) * (k - f)


def _extract_assistant_text(openai_like: Dict[str, Any]) -> str:
    """
    Expected vLLM OpenAI compatible response:
    {"choices":[{"message":{"content":"..."}}], ...}
    """
    try:
        return openai_like["choices"][0]["message"]["content"]
    except Exception:
        return ""


def _http_post_json(url: str, headers: Dict[str, str], payload: Dict[str, Any], timeout_s: int) -> Tuple[int, str]:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    for k, v in headers.items():
        req.add_header(k, v)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        # unify error as pseudo-status 0
        return 0, f"__CLIENT_ERROR__ {repr(e)}"


def _try_parse_json_strict(text: str) -> Tuple[bool, Optional[Any], str]:
    """
    Strict JSON parse. Some models sometimes wrap JSON with ```json ...```.
    We'll attempt strict first, then a minimal cleanup.
    """
    # strict
    try:
        return True, json.loads(text), "strict"
    except Exception:
        pass

    # minimal cleanup: remove fenced code blocks if present
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        # sometimes starts with json\n
        cleaned = cleaned.replace("json\n", "", 1).strip()
    # also try to extract first {...} block if present
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = cleaned[start : end + 1]
        try:
            return True, json.loads(candidate), "extracted_object"
        except Exception:
            pass

    return False, None, "failed"


# --------------------------
# GPU monitor helpers (VRAM)
# --------------------------
def _nvidia_smi_available() -> bool:
    return which("nvidia-smi") is not None


def _query_gpu_once() -> Optional[Tuple[str, int, int, int]]:
    """
    Returns (timestamp_str, mem_used_mb, mem_total_mb, util_gpu_pct)
    or None if failed.
    """
    try:
        out = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=timestamp,memory.used,memory.total,utilization.gpu",
                "--format=csv,noheader,nounits",
            ],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        # If multiple GPUs, take first line (you have 1 GPU in your logs)
        line = out.splitlines()[0].strip()
        parts = [p.strip() for p in line.split(",")]
        ts = parts[0]
        mem_used = int(float(parts[1]))
        mem_total = int(float(parts[2]))
        util = int(float(parts[3]))
        return ts, mem_used, mem_total, util
    except Exception:
        return None


class GPUMonitor:
    def __init__(self, csv_path: Path, interval_s: float = 1.0) -> None:
        self.csv_path = csv_path
        self.interval_s = interval_s
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

        self.samples: List[Tuple[str, int, int, int]] = []
        self.peak_used_mb: int = 0
        self.total_mb: Optional[int] = None
        self.enabled: bool = _nvidia_smi_available()

    def start(self) -> None:
        if not self.enabled:
            return

        self.csv_path.parent.mkdir(parents=True, exist_ok=True)
        self.csv_path.write_text("timestamp,memory_used_mb,memory_total_mb,util_gpu_pct\n", encoding="utf-8")

        def loop() -> None:
            while not self._stop.is_set():
                s = _query_gpu_once()
                if s is not None:
                    ts, used, total, util = s
                    self.samples.append(s)
                    if used > self.peak_used_mb:
                        self.peak_used_mb = used
                    self.total_mb = total
                    with self.csv_path.open("a", encoding="utf-8") as f:
                        f.write(f"{ts},{used},{total},{util}\n")
                time.sleep(self.interval_s)

        self._thread = threading.Thread(target=loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if not self.enabled:
            return
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
# --------------------------


def main() -> None:
    ap = argparse.ArgumentParser(description="FormDev bench runner (Lot 0) – prompts + metrics + outputs.")
    ap.add_argument("--prompts", default="bench/prompts.json", help="Path to prompts JSON file")
    ap.add_argument("--outdir", default="bench/results", help="Output directory")
    ap.add_argument("--api-url", default=DEFAULT_API_URL, help="Gateway URL (FastAPI) /v1/chat")
    ap.add_argument("--api-key", default=DEFAULT_API_KEY, help="X-API-Key value")
    ap.add_argument("--model", default=DEFAULT_MODEL, help="Model id to send in payload (optional)")
    ap.add_argument("--repeat", type=int, default=1, help="Repeat each test N times (latency stats)")
    ap.add_argument("--timeout", type=int, default=180, help="HTTP timeout seconds per request")

    # --- added (GPU monitor options, defaults chosen to not disturb existing usage) ---
    ap.add_argument("--vram-interval", type=float, default=1.0, help="nvidia-smi sampling interval in seconds")
    ap.add_argument("--no-vram", action="store_true", help="Disable VRAM monitoring (nvidia-smi)")
    # -------------------------------------------------------------------------------

    args = ap.parse_args()

    prompts_path = Path(args.prompts)
    outdir = Path(args.outdir) / _now_tag()
    outdir.mkdir(parents=True, exist_ok=True)

    # --- added (start VRAM monitor in background; separate thread, no impact on request payloads) ---
    vram_csv = outdir / "vram.csv"
    gpu_mon = GPUMonitor(vram_csv, interval_s=max(0.2, float(args.vram_interval)))
    if args.no_vram:
        gpu_mon.enabled = False
    gpu_mon.start()
    # ---------------------------------------------------------------------------------------------

    suite = json.loads(prompts_path.read_text(encoding="utf-8"))
    tests = suite["tests"]

    if not args.api_key:
        # stop monitor before exiting
        gpu_mon.stop()
        raise SystemExit("API_KEY missing. Provide --api-key or export API_KEY=...")

    headers = {"X-API-Key": args.api_key}

    run_meta = {
        "suite_name": suite.get("suite_name", "unknown"),
        "api_url": args.api_url,
        "model_payload": args.model,
        "repeat": args.repeat,
        "timeout_s": args.timeout,
        "started_at": datetime.now().isoformat(timespec="seconds"),

        # --- added ---
        "vram_monitoring_enabled": bool(gpu_mon.enabled),
        "vram_sampling_interval_s": None if not gpu_mon.enabled else gpu_mon.interval_s,
        "vram_csv": str(vram_csv),
        # -----------
    }

    all_results: List[Dict[str, Any]] = []
    all_latencies: List[float] = []

    try:
        for t in tests:
            test_id = t["id"]
            prompt = t["prompt"]
            max_tokens = int(t.get("max_tokens", 256))
            expects = t.get("expects", {"type": "text"})

            per_attempt: List[Dict[str, Any]] = []
            latencies: List[float] = []
            json_ok_count = 0
            must_contain_ok_count = 0

            for i in range(args.repeat):
                payload: Dict[str, Any] = {
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": max_tokens,
                }
                if args.model:
                    payload["model"] = args.model

                t0 = time.perf_counter()
                status, body = _http_post_json(args.api_url, headers, payload, timeout_s=args.timeout)
                t1 = time.perf_counter()
                dt_ms = (t1 - t0) * 1000.0
                latencies.append(dt_ms)
                all_latencies.append(dt_ms)

                parsed: Optional[Dict[str, Any]] = None
                assistant_text = ""
                parse_error = None

                if status == 200:
                    try:
                        parsed = json.loads(body)
                        assistant_text = _extract_assistant_text(parsed)
                    except Exception as e:
                        parse_error = repr(e)

                # validations
                json_ok = None
                json_parse_mode = None
                json_obj = None
                if expects.get("type") == "json" and status == 200:
                    ok, obj, mode = _try_parse_json_strict(assistant_text)
                    json_ok = ok
                    json_parse_mode = mode
                    json_obj = obj
                    if ok:
                        json_ok_count += 1

                must_contain = expects.get("must_contain")
                must_contain_ok = None
                if isinstance(must_contain, str) and status == 200:
                    must_contain_ok = (must_contain in assistant_text)
                    if must_contain_ok:
                        must_contain_ok_count += 1

                per_attempt.append(
                    {
                        "attempt": i + 1,
                        "http_status": status,
                        "latency_ms": dt_ms,
                        "raw_body": body,
                        "assistant_text": assistant_text,
                        "json_expected": expects.get("type") == "json",
                        "json_ok": json_ok,
                        "json_parse_mode": json_parse_mode,
                        "json_obj": json_obj,
                        "must_contain": must_contain,
                        "must_contain_ok": must_contain_ok,
                        "parse_error": parse_error,
                    }
                )

            # summarize this test
            test_summary = {
                "id": test_id,
                "project": t.get("project"),
                "repeat": args.repeat,
                "latency_ms": {
                    "mean": statistics.mean(latencies),
                    "p95": _percentile(latencies, 0.95),
                    "min": min(latencies),
                    "max": max(latencies),
                },
                "http_ok_rate": sum(1 for a in per_attempt if a["http_status"] == 200) / args.repeat,
                "json_ok_rate": (json_ok_count / args.repeat) if expects.get("type") == "json" else None,
                "must_contain_ok_rate": (must_contain_ok_count / args.repeat)
                if isinstance(expects.get("must_contain"), str)
                else None,
            }

            all_results.append({"test": t, "summary": test_summary, "attempts": per_attempt})

            # write per-test file
            (outdir / f"{test_id}.json").write_text(
                json.dumps(all_results[-1], ensure_ascii=False, indent=2), encoding="utf-8"
            )
    finally:
        # make sure monitor is stopped even if a test fails
        gpu_mon.stop()

    # --- added: finalize VRAM peak ---
    vram_info = {
        "vram_peak_mb": None if not gpu_mon.enabled else gpu_mon.peak_used_mb,
        "vram_total_mb": None if not gpu_mon.enabled else gpu_mon.total_mb,
        "vram_samples": None if not gpu_mon.enabled else len(gpu_mon.samples),
    }
    (outdir / "vram_summary.json").write_text(json.dumps(vram_info, ensure_ascii=False, indent=2), encoding="utf-8")
    # --------------------------------

    # global summary
    global_summary = {
        "meta": {
            **run_meta,
            # --- added ---
            **vram_info,
            "ended_at": datetime.now().isoformat(timespec="seconds"),
            # -----------
        },
        "global_latency_ms": {
            "mean": statistics.mean(all_latencies) if all_latencies else None,
            "p95": _percentile(all_latencies, 0.95) if all_latencies else None,
            "min": min(all_latencies) if all_latencies else None,
            "max": max(all_latencies) if all_latencies else None,
        },
        "tests": [r["summary"] for r in all_results],
    }

    (outdir / "summary.json").write_text(json.dumps(global_summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Done. Results saved to: {outdir}")
    print(f"Summary: {outdir / 'summary.json'}")
    if gpu_mon.enabled:
        print(f"VRAM: peak={gpu_mon.peak_used_mb} MB total={gpu_mon.total_mb} MB csv={vram_csv}")
    else:
        print("VRAM monitoring disabled or nvidia-smi not available.")


if __name__ == "__main__":
    main()