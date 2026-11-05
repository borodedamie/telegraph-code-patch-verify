#!/usr/bin/env python3
"""Robustness checks for the CODE_PATCH_VERIFY truth sources, against live data.

  1. pending      commits whose CI is still running give no verdict (never a guess)
  2. reruns       a re-run CI job: the source reports the latest attempt
  3. rate limits  a refused or rate-limited call gives no verdict, not a wrong one
  4. cross-host   each source is asked about the other hosts' commits; with up to three
                  sources per question, answering for a commit it does not host is how
                  sources could disagree
Results: results/robustness.json, summary on stdout.

    GH_TOKEN=$(gh auth token) python work/benchmark/robustness.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from run_truth_sources import url_for, verdict  # noqa: E402  same URL building and verdict rule

HERE = Path(__file__).parent
TOKEN = os.environ.get("GH_TOKEN")


def get(url: str, auth: bool = True) -> tuple[int, dict | list | None, dict]:
    # Headers and body go to separate files: no header/body splitting to get wrong.
    with tempfile.TemporaryDirectory() as tmp:
        hf, bf = os.path.join(tmp, "h"), os.path.join(tmp, "b")
        cmd = ["curl", "-sL", "-m", "30", "-D", hf, "-o", bf, "-H", "Accept: application/json", "-A", "cpv-robustness"]
        if auth and TOKEN and "api.github.com" in url:
            cmd += ["-H", f"Authorization: Bearer {TOKEN}"]
        subprocess.run(cmd + [url], capture_output=True)
        lines = [l.strip() for l in open(hf, encoding="latin-1")] if os.path.exists(hf) else []
        body = open(bf, encoding="utf-8", errors="replace").read() if os.path.exists(bf) else ""
    status = next((int(l.split()[1]) for l in reversed(lines) if l.startswith("HTTP/")), 0)
    headers = {l.split(":", 1)[0].lower(): l.split(":", 1)[1].strip() for l in lines if ":" in l and not l.startswith("HTTP/")}
    try:
        return status, json.loads(body), headers
    except Exception:
        return status, None, headers


def source_verdict(provider: str, params: dict, auth: bool = True) -> tuple[str | None, str]:
    code, body, _ = get(url_for(provider, params), auth)
    if code != 200 or not isinstance(body, dict):
        return None, f"HTTP {code}"
    return verdict(provider, body)


def params_for(provider: str, repo: str, sha: str) -> dict:
    owner, _, name = repo.partition("/")
    if provider == "gitlab":
        return {"project": urllib.parse.quote(repo, safe=""), "sha": sha}
    return {"owner": owner, "repo": name, "ref": sha}


def pending() -> list[dict]:
    out = []
    for repo in ["vitest-dev/vitest", "fastify/fastify", "nestjs/nest", "pydantic/pydantic"]:
        _, runs, _ = get(f"https://api.github.com/repos/{repo}/actions/runs?status=in_progress&per_page=3")
        for r in (runs or {}).get("workflow_runs", [])[:2]:
            v, note = source_verdict("github", params_for("github", repo, r["head_sha"]))
            out.append({"host": "github", "repo": repo, "sha": r["head_sha"], "verdict": v, "note": note})
    for project in ["gitlab-org/gitlab-runner", "gitlab-org/gitaly", "gitlab-org/cli"]:
        enc = urllib.parse.quote(project, safe="")
        _, pls, _ = get(f"https://gitlab.com/api/v4/projects/{enc}/pipelines?status=running&per_page=3")
        for p in (pls or [])[:2]:
            if p.get("source") not in {"push", "merge_request_event"}:
                continue
            v, note = source_verdict("gitlab", params_for("gitlab", project, p["sha"]))
            out.append({"host": "gitlab", "repo": project, "sha": p["sha"], "verdict": v, "note": note})
    for repo in ["forgejo/forgejo", "Codeberg/Documentation"]:
        _, prs, _ = get(f"https://codeberg.org/api/v1/repos/{repo}/pulls?state=open&limit=20")
        for pr in (prs or [])[:20]:
            sha = pr["head"]["sha"]
            _, st, _ = get(f"https://codeberg.org/api/v1/repos/{repo}/commits/{sha}/status")
            if (st or {}).get("state") == "pending":
                v, note = source_verdict("codeberg", params_for("codeberg", repo, sha))
                out.append({"host": "codeberg", "repo": repo, "sha": sha, "verdict": v, "note": note})
                break
    for r in out:
        r["ok"] = r["verdict"] is None  # a running commit must not get a verdict
    return out


def reruns() -> list[dict]:
    """Commits whose latest workflow attempt differs from attempt 1; the suite must follow the latest."""
    out = []
    for repo in ["pydantic/pydantic", "typeorm/typeorm", "honojs/hono", "encode/httpx", "fastify/fastify", "vitest-dev/vitest"]:
        _, runs, _ = get(f"https://api.github.com/repos/{repo}/actions/runs?status=completed&per_page=100&page=1")
        for r in (runs or {}).get("workflow_runs", []):
            if r.get("run_attempt", 1) < 2 or len(out) >= 8:
                continue
            _, first, _ = get(f"https://api.github.com/repos/{repo}/actions/runs/{r['id']}/attempts/1")
            if not first or first.get("conclusion") == r["conclusion"]:
                continue
            code, suites, _ = get(f"https://api.github.com/repos/{repo}/commits/{r['head_sha']}/check-suites?per_page=100")
            suite = next((s for s in (suites or {}).get("check_suites", []) if s["id"] == r["check_suite_id"]), None)
            out.append({"repo": repo, "sha": r["head_sha"], "workflow": r["name"], "attempt1": first.get("conclusion"),
                        "latest_attempt": r["run_attempt"], "latest": r["conclusion"],
                        "suite_reports": suite and suite["conclusion"],
                        "ok": bool(suite) and suite["conclusion"] == r["conclusion"]})
    return out


def rate_limits() -> dict:
    code, _, h = get("https://api.github.com/rate_limit", auth=False)
    bogus_v, bogus_note = source_verdict("github", {"owner": "fastify", "repo": "fastify", "ref": "0" * 40})
    missing_v, missing_note = source_verdict("gitlab", {"project": "no-such%2Fproject-xyz", "sha": "deadbeef"})
    return {
        "github_keyless_limit_per_hour": h.get("x-ratelimit-limit"),
        "github_keyless_remaining": h.get("x-ratelimit-remaining"),
        "unknown_commit": {"verdict": bogus_v, "note": bogus_note, "ok": bogus_v is None},
        "unknown_project": {"verdict": missing_v, "note": missing_note, "ok": missing_v is None},
        "refused_call": {"verdict": verdict_on_refusal(), "ok": verdict_on_refusal() is None},
    }


def verdict_on_refusal() -> str | None:
    """A 403/429 body (GitHub's rate-limit reply) carries no suites, so no verdict."""
    v, _ = verdict("github", {"message": "API rate limit exceeded", "documentation_url": "https://docs.github.com"})
    return v


def cross_host() -> list[dict]:
    rows = [json.loads(l) for f in ("benchmark.jsonl", "holdout.jsonl")
            for l in (HERE / f).read_text().splitlines() if l.strip()]
    out = []
    for r in rows:
        for other in ("github", "gitlab", "codeberg"):
            if other == r["provider"]:
                continue
            v, note = source_verdict(other, params_for(other, r["repo"], r["sha"]))
            out.append({"id": r["id"], "commit_host": r["provider"], "source": other, "label": r["label"],
                        "verdict": v, "note": note, "contradicts": v is not None and v != r["label"]})
    return out


def main() -> int:
    res = {"pending": pending(), "reruns": reruns(), "rate_limits": rate_limits(), "cross_host": cross_host()}
    (HERE / "results").mkdir(exist_ok=True)
    (HERE / "results/robustness.json").write_text(json.dumps(res, indent=1))
    p, rr, rl, ch = res["pending"], res["reruns"], res["rate_limits"], res["cross_host"]
    print(f"pending:     {sum(x['ok'] for x in p)}/{len(p)} running commits gave no verdict")
    for x in p:
        print(f"   {x['host']:8} {x['repo']:26} {x['sha'][:10]} -> {x['verdict']} ({x['note']})")
    print(f"reruns:      {sum(x['ok'] for x in rr)}/{len(rr)} re-run commits reported the latest attempt")
    for x in rr:
        print(f"   {x['repo']:22} {x['sha'][:10]} {x['workflow'][:28]:28} attempt1={x['attempt1']} latest(#{x['latest_attempt']})={x['latest']} suite={x['suite_reports']}")
    print(f"rate limits: GitHub keyless limit {rl['github_keyless_limit_per_hour']}/hour; unknown commit -> {rl['unknown_commit']['verdict']} "
          f"({rl['unknown_commit']['note']}); unknown project -> {rl['unknown_project']['verdict']} ({rl['unknown_project']['note']}); "
          f"rate-limit reply -> {rl['refused_call']['verdict']}")
    answered = [x for x in ch if x["verdict"] is not None]
    print(f"cross-host:  {len(ch)} calls to sources on commits they do not host; {len(answered)} gave a verdict, "
          f"{sum(x['contradicts'] for x in ch)} contradicted the label")
    for x in answered[:10]:
        print(f"   {x['id']} {x['commit_host']} commit via {x['source']}: {x['verdict']} vs label {x['label']} ({x['note']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
