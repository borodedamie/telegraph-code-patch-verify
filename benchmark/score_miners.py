#!/usr/bin/env python3
"""Score the miners registered on CODE_PATCH_VERIFY_GENERAL against the benchmark.

Each miner is called exactly as its registered YAML declares (miners/<slug>.yaml):
base_url + external_path, with parameters filled from the benchmark commit as generously
as a perfect request builder could. A parameter the commit cannot supply keeps the
miner's own default. The response is read for a pass/fail verdict with one generous rule
for every miner (see verdict()). A miner that returns no verdict scores it as wrong.

Sample: a fixed, balanced draw from benchmark.jsonl + holdout.jsonl (seed 0).

    GH_TOKEN=$(gh auth token) python work/benchmark/score_miners.py
"""

from __future__ import annotations

import json
import os
import random
import re
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path

import yaml

HERE = Path(__file__).parent
SAMPLE = {"github": 24, "gitlab": 12, "codeberg": 12}  # balanced pass/fail within each
PASS_WORDS = {"success", "succeeded", "passed", "pass", "true", "yes", "ok", "green"}
FAIL_WORDS = {"failure", "failed", "fail", "error", "errored", "false", "no", "timed_out",
              "cancelled", "canceled", "action_required", "startup_failure", "red"}


def sample() -> list[dict]:
    rows = [json.loads(l) for f in ("benchmark.jsonl", "holdout.jsonl")
            for l in (HERE / f).read_text().splitlines() if l.strip()]
    rng = random.Random(0)
    out = []
    for prov, n in SAMPLE.items():
        for label in ("pass", "fail"):
            pool = [r for r in rows if r["provider"] == prov and r["label"] == label]
            out += rng.sample(pool, n // 2)
    return out


def fill(slug: str, c: dict) -> dict:
    """Best-case parameters for one commit; keys absent here keep the miner's default."""
    owner, _, repo = c["repo"].partition("/")
    sha = c["sha"]
    patch = f"{c['repo']}@{sha}"
    gh = c["provider"] == "github"
    return {
        "patch-gh-commit-check": {"owner": owner, "repo": repo} if gh else {},
        "patch-gh-commit": {"owner": owner, "repo": repo, "ref": sha} if gh else {},
        "patch-gh-commits-list": {"owner": owner, "repo": repo, "sha": sha} if gh else {},
        "patch-gh-compare": {"owner": owner, "repo": repo, "basehead": f"{sha}~1...{sha}"} if gh else {},
        "patch-gh-compare-react": {"owner": owner, "repo": repo, "basehead": f"{sha}~1...{sha}"} if gh else {},
        "patch-gh-actions-requests-tests": {"owner": owner, "repo": repo} if gh else {},
        "patch-gh-pr-files": {"owner": owner, "repo": repo} if gh else {},
        "patch-gitlab-compare": ({"project": urllib.parse.quote(c["repo"], safe=""), "from": f"{sha}~1", "to": sha}
                                 if c["provider"] == "gitlab" else {}),
        "patch-npm-pkg": {"pkg": repo},
        "patch-npm-react": {"pkg": repo},
        "codewire-code-patch-verify": {"patch": patch},
        "zk-code-ci": {"patch": c.get("run_url") or patch},
        "zk-patchproof": {"patch": patch},
        "telegraph-verity-intelligence": {"intent": "CODE_PATCH_VERIFY_GENERAL",
                                          "input": f"Did the CI checks for commit {sha} of {c['repo']} pass?"},
    }.get(slug, {})


def request_for(y: dict, slug: str, c: dict) -> tuple[str, str, dict | None]:
    ep = (y.get("endpoints") or [{}])[0]
    defaults = {k: v.get("default") for k, v in ((y.get("input_schema") or {}).get("properties") or {}).items()
                if isinstance(v, dict) and v.get("default") is not None}
    vals = {**defaults, **fill(slug, c)}
    path = ep.get("external_path") or ep.get("path") or "/"
    path = re.sub(r"\{(\w+)\}", lambda m: urllib.parse.quote(str(vals.get(m.group(1), m.group(0))), safe="%~."), path)
    query, body = {}, {}
    for loc, groups in (ep.get("params") or {}).items():
        for p in [p for g in (groups or {}).values() for p in (g or [])]:
            if p["name"] in vals and loc == "query":
                query[p["name"]] = vals[p["name"]]
            elif p["name"] in vals and loc == "body":
                body[p["name"]] = vals[p["name"]]
    if not (ep.get("params") or {}) and "patch" in vals:  # endpoint documents ?patch= in its description
        query["patch"] = vals["patch"]
    if slug == "patch-gh-commits-list":
        query["sha"] = vals.get("sha")
    url = y["base_url"].rstrip("/") + path
    if query:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode({k: v for k, v in query.items() if v is not None})
    return (ep.get("method") or "GET").upper(), url, body or None


def call(method: str, url: str, body: dict | None, token: str | None) -> tuple[int, str]:
    cmd = ["curl", "-sL", "-m", "60", "-o", "-", "-w", "\n%{http_code}", "-X", method,
           "-H", "Accept: application/json", "-A", "cpv-benchmark"]
    if token and "api.github.com" in url:
        cmd += ["-H", f"Authorization: Bearer {token}"]
    if body is not None:
        cmd += ["-H", "Content-Type: application/json", "-d", json.dumps(body)]
    for attempt in range(4):
        out = subprocess.run(cmd + [url], capture_output=True, text=True).stdout
        text, _, code = out.rpartition("\n")
        code = int(code or 0)
        upstream_limited = "upstream_rate_limit" in text
        if code not in (429, 500, 502, 503, 504) and not upstream_limited:
            break
        time.sleep(10 * (attempt + 1))  # back off; the miner or its upstream is rate-limited
    return code, text


def verdict(text: str) -> tuple[str | None, str]:
    """Generous reading: the first CI-style outcome the response states."""
    try:
        d = json.loads(text)
    except Exception:
        d = None
    if isinstance(d, dict):
        for key in ("check_suites", "check_runs", "workflow_runs"):
            if isinstance(d.get(key), list) and d[key]:
                concl = [x.get("conclusion") for x in d[key] if x.get("conclusion")]
                if not concl:
                    return None, f"{key}: none completed"
                bad = [x for x in concl if x in FAIL_WORDS]
                return ("fail" if bad else "pass"), f"{key}: {','.join(sorted(set(concl)))}"
        if isinstance(d.get("exit_status"), int):  # code sandboxes: a clean exit read as a pass
            return ("pass" if d["exit_status"] == 0 else "fail"), f"exit_status={d['exit_status']}"
        if "passed" in d and isinstance(d["passed"], bool):
            return ("pass" if d["passed"] else "fail"), f"passed={d['passed']}"
        for key in ("conclusion", "status", "state", "outcome", "result", "verdict"):
            v = d.get(key)
            if isinstance(v, str) and v.lower() in PASS_WORDS | FAIL_WORDS:
                return ("pass" if v.lower() in PASS_WORDS else "fail"), f"{key}={v}"
    if isinstance(d, list) and d and isinstance(d[0], dict):
        v = d[0].get("status") or d[0].get("outcome") or d[0].get("conclusion")
        if isinstance(v, str) and v.lower() in PASS_WORDS | FAIL_WORDS:
            return ("pass" if v.lower() in PASS_WORDS else "fail"), f"[0].status={v}"
    m = re.search(r'"(?:passed|conclusion|verdict|outcome)"\s*:\s*"?(\w+)"?', text or "")
    if m and m.group(1).lower() in PASS_WORDS | FAIL_WORDS:
        return ("pass" if m.group(1).lower() in PASS_WORDS else "fail"), f"text {m.group(0)[:40]}"
    return None, "no CI verdict in response"


def main() -> int:
    token = os.environ.get("GH_TOKEN")
    commits = sample()
    for c in commits:  # the latest Actions run URL for each GitHub commit (what a user would paste)
        if c["provider"] == "github":
            code, text = call("GET", f"https://api.github.com/repos/{c['repo']}/actions/runs?head_sha={c['sha']}&per_page=1", None, token)
            runs = json.loads(text).get("workflow_runs", []) if code == 200 else []
            c["run_url"] = runs[0]["html_url"] if runs else None
    index = {m["slug"]: m for m in json.loads((HERE / "miners/index.json").read_text())}
    results, cache = {}, {}
    for slug in sorted(index):
        f = HERE / f"miners/{slug}.yaml"
        if not f.exists():
            continue
        y = yaml.safe_load(f.read_text())
        rows = []
        for c in commits:
            method, url, body = request_for(y, slug, c)
            key = (method, url, json.dumps(body))
            if key not in cache:
                cache[key] = call(method, url, body, token)
                if "api.github.com" not in url:
                    time.sleep(2.0)  # be polite to third-party services
            code, text = cache[key]
            got, note = verdict(text) if code == 200 else (None, f"HTTP {code}")
            rows.append({"id": c["id"], "provider": c["provider"], "label": c["label"], "verdict": got,
                         "correct": got == c["label"], "note": note, "url": url})
        results[slug] = rows
        n = len(rows)
        print(f"{slug:32} correct {sum(r['correct'] for r in rows):>2}/{n}  answered {sum(r['verdict'] is not None for r in rows):>2}/{n}"
              f"  distinct requests {len({r['url'] for r in rows}):>2}  network rank {index[slug]['rank']} score {index[slug]['score']}",
              flush=True)
    (HERE / "results").mkdir(exist_ok=True)
    (HERE / "results/miners.json").write_text(json.dumps({"sample": [c["id"] for c in commits], "results": results}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
