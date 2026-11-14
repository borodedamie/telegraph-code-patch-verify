#!/usr/bin/env python3
"""Collect the CI record behind each development-set commit, as the facts for question pairs.

Only benchmark/benchmark.jsonl is used; benchmark/holdout.jsonl stays unseen so it can test
the evaluator adapter later. Output: pairs/evidence.jsonl, one commit per line with its
workflows (GitHub), pipeline jobs (GitLab) or status contexts (Codeberg).

    GH_TOKEN=$(gh auth token) python pairs/collect_evidence.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOKEN = os.environ.get("GH_TOKEN")


def get(url: str):
    cmd = ["curl", "-sL", "-m", "30", "-H", "Accept: application/json", "-A", "cpv-pairs"]
    if TOKEN and "api.github.com" in url:
        cmd += ["-H", f"Authorization: Bearer {TOKEN}"]
    out = subprocess.run(cmd + [url], capture_output=True, text=True).stdout
    try:
        return json.loads(out)
    except Exception:
        return None


def github(r: dict) -> dict:
    repo, sha = r["repo"], r["sha"]
    runs = (get(f"https://api.github.com/repos/{repo}/actions/runs?head_sha={sha}&per_page=100") or {}).get("workflow_runs", [])
    workflows = []
    for w in runs:
        jobs = (get(f"https://api.github.com/repos/{repo}/actions/runs/{w['id']}/jobs?per_page=100") or {}).get("jobs", [])
        failed = [j["name"] for j in jobs if j.get("conclusion") in {"failure", "timed_out"}]
        workflows.append({"name": w["name"], "event": w["event"], "conclusion": w["conclusion"],
                          "attempt": w.get("run_attempt", 1), "jobs": len(jobs), "failed_jobs": failed[:6],
                          "url": w["html_url"]})
    commit = get(f"https://api.github.com/repos/{repo}/commits/{sha}") or {}
    msg = ((commit.get("commit") or {}).get("message") or "").split("\n")[0][:120]
    return {"workflows": workflows, "message": msg}


def gitlab(r: dict) -> dict:
    enc = urllib.parse.quote(r["repo"], safe="")
    pls = [p for p in (get(f"https://gitlab.com/api/v4/projects/{enc}/pipelines?sha={r['sha']}") or [])
           if p.get("source") in {"push", "merge_request_event"}]
    if not pls:
        return {"jobs": [], "message": ""}
    p = max(pls, key=lambda x: x["id"])
    jobs = get(f"https://gitlab.com/api/v4/projects/{enc}/pipelines/{p['id']}/jobs?per_page=100") or []
    commit = get(f"https://gitlab.com/api/v4/projects/{enc}/repository/commits/{r['sha']}") or {}
    return {"pipeline": {"id": p["id"], "status": p["status"], "source": p["source"], "url": p["web_url"]},
            "jobs": [{"name": j["name"], "stage": j["stage"], "status": j["status"],
                      "allow_failure": j.get("allow_failure", False)} for j in jobs],
            "message": (commit.get("title") or "")[:120]}


def codeberg(r: dict) -> dict:
    statuses = get(f"https://codeberg.org/api/v1/repos/{r['repo']}/commits/{r['sha']}/statuses?limit=100") or []
    latest: dict[str, dict] = {}
    for s in statuses:
        if s["context"] not in latest or s["id"] > latest[s["context"]]["id"]:
            latest[s["context"]] = s
    commit = get(f"https://codeberg.org/api/v1/repos/{r['repo']}/git/commits/{r['sha']}") or {}
    return {"contexts": [{"context": c, "status": s["status"], "description": (s.get("description") or "")[:80]}
                         for c, s in sorted(latest.items())],
            "message": (((commit.get("commit") or {}).get("message")) or "").split("\n")[0][:120]}


def main() -> int:
    # --holdout: the held-out commits, for test pairs only (never training data); --expand: more dev commits
    src, dst = (("holdout", "holdout_evidence") if "--holdout" in sys.argv else
                ("expand", "expand_evidence") if "--expand" in sys.argv else ("benchmark", "evidence"))
    rows = [json.loads(l) for l in (ROOT / f"benchmark/{src}.jsonl").read_text().splitlines() if l.strip()]
    out = []
    for r in rows:
        ev = {"github": github, "gitlab": gitlab, "codeberg": codeberg}[r["provider"]](r)
        out.append({**{k: r[k] for k in ("id", "provider", "repo", "sha", "label", "web")}, **ev})
        print(f"{r['id']} {r['provider']:8} {r['repo']:26} {r['label']:4} "
              f"{len(ev.get('workflows') or ev.get('jobs') or ev.get('contexts') or [])} items", flush=True)
    (ROOT / f"pairs/{dst}.jsonl").write_text("".join(json.dumps(o) + "\n" for o in out))
    print(f"wrote {len(out)} commits -> pairs/{dst}.jsonl")
    return 0


if __name__ == "__main__":
    sys.exit(main())
