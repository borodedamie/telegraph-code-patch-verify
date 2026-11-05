#!/usr/bin/env python3
"""Validate the truth sources against the benchmark.

For every benchmark commit, calls the matching truth source exactly as its YAML declares
(base_url + external_path with the commit's params), reads the verdict, and compares it
with the independently derived reference label.

Verdict rules mirror the intent's response format ("passed" is true only for success):
  github    check suites (ignoring never-started app suites with 0 runs); any not completed ->
            no verdict; any failure, timed_out, cancelled, action_required or startup_failure
            -> fail; all success/skipped/neutral -> pass
  gitlab    status success -> pass; failed/canceled/skipped -> fail; else no verdict
  codeberg  state success -> pass; failure/error -> fail; else no verdict

Limitation: on the network a parser model reads the raw answer; this script applies the
rule above in code, so it measures whether the SOURCE carries the right answer.

    python work/benchmark/run_truth_sources.py            # keyless, as the node calls them
    GH_TOKEN=$(gh auth token) python work/benchmark/run_truth_sources.py   # lifts GitHub's 60/hour cap
"""

from __future__ import annotations

import json
import os
import re
import statistics
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import yaml

HERE = Path(__file__).parent
SOURCES = {
    "github": HERE.parent / "truth_sources/github-check-suites.yaml",
    "gitlab": HERE.parent / "truth_sources/gitlab-commit-status.yaml",
    "codeberg": HERE.parent / "truth_sources/codeberg-commit-status.yaml",
}
BAD = {"failure", "timed_out", "cancelled", "action_required", "startup_failure"}
OK = {"success", "skipped", "neutral"}


def url_for(provider: str, params: dict) -> str:
    y = yaml.safe_load(SOURCES[provider].read_text())
    path = y["endpoints"][0]["external_path"]
    return y["base_url"] + re.sub(r"\{(\w+)\}", lambda m: params[m.group(1)], path)


def verdict(provider: str, body: dict) -> tuple[str | None, str]:
    if provider == "github":
        suites = [x for x in body.get("check_suites", [])
                  if not (x["status"] != "completed" and x.get("latest_check_runs_count", 0) == 0)]
        if not suites:
            return None, "no check suites"
        note = f"{len(suites)} suites"
        if body.get("total_count", 0) > len(body.get("check_suites", [])):
            note += f" (truncated, {body['total_count']} total)"
        if any(x["status"] != "completed" for x in suites):
            return None, note + ", some not completed"
        concl = [x["conclusion"] for x in suites]
        if any(c in BAD for c in concl):
            return "fail", note + ", " + ",".join(sorted(set(concl)))
        if all(c in OK for c in concl):
            return "pass", note + ", " + ",".join(sorted(set(concl)))
        return None, note + ", unrecognised conclusion"
    if provider == "gitlab":
        s = body.get("status")
        return ("pass" if s == "success" else "fail" if s in {"failed", "canceled", "skipped"} else None), f"status={s}"
    s = body.get("state")
    return ("pass" if s == "success" else "fail" if s in {"failure", "error"} else None), f"state={s}"


def main() -> int:
    token = os.environ.get("GH_TOKEN")
    bench = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "benchmark.jsonl"
    rows = [json.loads(l) for l in bench.read_text().splitlines() if l.strip()]
    results = []
    for r in rows:
        url = url_for(r["provider"], r["params"])
        headers = {"Accept": "application/json", "User-Agent": "cpv-benchmark"}
        if token and r["provider"] == "github":
            headers["Authorization"] = f"Bearer {token}"
        t0 = time.monotonic()
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as resp:
                body = json.load(resp)
            got, note = verdict(r["provider"], body)
            err = None
        except urllib.error.HTTPError as e:
            got, note, err = None, "", f"HTTP {e.code}"
        except Exception as e:  # noqa: BLE001 - record the failure, keep going
            got, note, err = None, "", type(e).__name__
        ms = round((time.monotonic() - t0) * 1000)
        results.append({**{k: r[k] for k in ("id", "provider", "repo", "sha", "label", "web")},
                        "verdict": got, "note": note, "error": err, "ms": ms,
                        "correct": got == r["label"] if got else None})

    (HERE / "results").mkdir(exist_ok=True)
    (HERE / f"results/truth_sources_{bench.stem}.json").write_text(json.dumps(results, indent=1))

    print(f"{'provider':9} {'n':>3} {'verdict':>8} {'correct':>8} {'accuracy':>9} {'TP':>3} {'TN':>3} {'FP':>3} {'FN':>3} {'p50 ms':>7}")
    for prov in ["github", "gitlab", "codeberg", "all"]:
        sub = [x for x in results if prov == "all" or x["provider"] == prov]
        if not sub:
            continue
        v = [x for x in sub if x["verdict"]]
        c = sum(x["correct"] for x in v)
        tp = sum(x["verdict"] == "pass" and x["label"] == "pass" for x in v)
        tn = sum(x["verdict"] == "fail" and x["label"] == "fail" for x in v)
        fp = sum(x["verdict"] == "pass" and x["label"] == "fail" for x in v)
        fn = sum(x["verdict"] == "fail" and x["label"] == "pass" for x in v)
        acc = f"{c / len(v):.1%}" if v else "-"
        print(f"{prov:9} {len(sub):>3} {len(v):>8} {c:>8} {acc:>9} {tp:>3} {tn:>3} {fp:>3} {fn:>3} {statistics.median(x['ms'] for x in sub):>7}")
    print("\nwrong or no verdict:")
    for x in results:
        if x["correct"] is not True:
            print(f"  {x['id']} {x['provider']:8} label={x['label']} verdict={x['verdict']} {x['error'] or x['note']}  {x['web']}")
    print(f"\nGitHub calls were {'authenticated (token)' if token else 'keyless'}; GitLab and Codeberg keyless.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
