#!/usr/bin/env python3
"""Build the CODE_PATCH_VERIFY benchmark: finished public commits with a known CI verdict.

Each commit's reference label is derived from a DIFFERENT record than the one the truth
source reads, so agreement between them is evidence rather than an echo:

  provider  reference label from                          truth source reads
  github    Actions workflow runs for the commit          check-runs for the commit
  gitlab    the pipeline's individual jobs (allow_failure) the commit's pipeline status
  codeberg  latest individual status per context           the combined status

Commits that are still running, cancelled or otherwise ambiguous are excluded, so every
label is a settled fact. Output: work/benchmark/benchmark.jsonl (one commit per line).

    GH_TOKEN=$(gh auth token) python work/benchmark/build_set.py
"""

from __future__ import annotations

import json
import os
import random
import sys
import urllib.parse
import urllib.request
from pathlib import Path

OUT = Path(__file__).with_name("benchmark.jsonl")
HOLDOUT = os.environ.get("HOLDOUT") == "1"  # a second, unseen set from different repos
PER_REPO = 6  # pass and fail each, per repo/project
GITHUB_REPOS = ["fastify/fastify", "nestjs/nest", "knex/knex", "typeorm/typeorm",
                "vitest-dev/vitest", "pydantic/pydantic"]
GITLAB_PROJECTS = ["gitlab-org/gitlab-runner", "gitlab-org/gitaly", "gitlab-org/cli"]
CODEBERG_REPOS = ["forgejo/forgejo"]
if HOLDOUT:
    OUT = Path(__file__).with_name("holdout.jsonl")
    PER_REPO = 4
    GITHUB_REPOS = ["sindresorhus/got", "encode/httpx", "honojs/hono", "date-fns/date-fns", "psf/requests"]
    GITLAB_PROJECTS = ["gitlab-org/gitlab-shell", "gitlab-org/gitlab-pages"]
    CODEBERG_REPOS = ["Codeberg/Documentation", "Codeberg/pages-server"]

PASS = {"success", "skipped", "neutral"}
CI_SOURCES = {"push", "merge_request_event"}
FAIL = {"failure", "timed_out"}


def get(url: str, token: str | None = None):
    headers = {"Accept": "application/json", "User-Agent": "cpv-benchmark"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as r:
        return json.load(r)


def github(repo: str, token: str) -> list[dict]:
    """Label = every Actions workflow run on the commit is completed; fail if any failed."""
    # Candidates from failed and successful runs; each is then re-checked across ALL its runs.
    shas: list[str] = []
    for st in ("failure", "success"):
        for page in (1, 2):
            runs = get(f"https://api.github.com/repos/{repo}/actions/runs?status={st}&per_page=100&page={page}", token)
            shas += [r["head_sha"] for r in runs["workflow_runs"]]
    shas = list(dict.fromkeys(shas))
    out = {"pass": [], "fail": []}
    for sha in shas:
        if all(len(v) >= PER_REPO for v in out.values()):
            break
        all_runs = get(f"https://api.github.com/repos/{repo}/actions/runs?head_sha={sha}&per_page=100", token)["workflow_runs"]
        if not all_runs or any(r["status"] != "completed" for r in all_runs):
            continue
        concl = [r["conclusion"] for r in all_runs]
        if any(c in FAIL for c in concl):
            label = "fail"
        elif all(c in PASS for c in concl) and "success" in concl:
            label = "pass"
        else:
            continue  # cancelled, action_required, stale...: not a settled verdict
        if len(out[label]) < PER_REPO:
            owner, name = repo.split("/")
            out[label].append({
                "provider": "github", "repo": repo, "sha": sha, "label": label,
                "reference": "actions workflow runs: " + ", ".join(sorted(set(concl))),
                "patch": f"{repo}@{sha[:10]}", "params": {"owner": owner, "repo": name, "ref": sha},
                "web": f"https://github.com/{repo}/commit/{sha}",
            })
    return out["pass"] + out["fail"]


def gitlab(project: str) -> list[dict]:
    """Label from the latest pipeline's jobs: fail if a job that may not fail failed."""
    enc = urllib.parse.quote(project, safe="")
    out = {"pass": [], "fail": []}
    for status in ("failed", "success"):
        for p in get(f"https://gitlab.com/api/v4/projects/{enc}/pipelines?status={status}&per_page=100"):
            label = "fail" if status == "failed" else "pass"
            if len(out[label]) >= PER_REPO:
                break
            if p.get("source") not in CI_SOURCES:
                continue  # e.g. duo_workflow: AI-agent workloads on refs/workloads/*, not the commit's CI
            sha = p["sha"]
            ci = [x for x in get(f"https://gitlab.com/api/v4/projects/{enc}/pipelines?sha={sha}") if x.get("source") in CI_SOURCES]
            if not ci or max(ci, key=lambda x: x["id"])["id"] != p["id"]:
                continue  # a newer CI pipeline exists for this commit; keep only clean cases
            jobs = get(f"https://gitlab.com/api/v4/projects/{enc}/pipelines/{p['id']}/jobs?per_page=100")
            jobs += get(f"https://gitlab.com/api/v4/projects/{enc}/pipelines/{p['id']}/bridges?per_page=100")
            if not jobs:
                continue
            hard_fail = any(j["status"] == "failed" and not j.get("allow_failure") for j in jobs)
            done = all(j["status"] in {"success", "failed", "skipped", "manual", "canceled"} for j in jobs)
            derived = "fail" if hard_fail else "pass" if done and any(j["status"] == "success" for j in jobs) else None
            if derived != label:
                continue  # jobs and pipeline disagree: ambiguous, leave it out
            n_failed = sum(j["status"] == "failed" for j in jobs)
            out[label].append({
                "provider": "gitlab", "repo": project, "sha": sha, "label": label,
                "reference": f"pipeline {p['id']} jobs: {len(jobs)} total, {n_failed} failed",
                "patch": f"{project}@{sha[:10]}", "params": {"project": enc, "sha": sha},
                "web": f"https://gitlab.com/{project}/-/commit/{sha}",
            })
    return out["pass"] + out["fail"]


def codeberg(repo: str) -> list[dict]:
    """Label from the latest status per context: fail if any context failed or errored."""
    out = {"pass": [], "fail": []}
    for pr in get(f"https://codeberg.org/api/v1/repos/{repo}/pulls?state=closed&limit=50"):
        if all(len(v) >= PER_REPO for v in out.values()):
            break
        sha = pr["head"]["sha"]
        statuses = get(f"https://codeberg.org/api/v1/repos/{repo}/commits/{sha}/statuses?limit=100")
        latest: dict[str, dict] = {}
        for s in statuses:
            if s["context"] not in latest or s["id"] > latest[s["context"]]["id"]:
                latest[s["context"]] = s
        states = [s["status"] for s in latest.values()]
        if not states or any(x in {"pending", "warning"} for x in states):
            continue
        if any(x in {"failure", "error"} for x in states):
            label = "fail"
        elif all(x in {"success", "skipped"} for x in states) and "success" in states:
            label = "pass"
        else:
            continue
        if len(out[label]) < PER_REPO:
            owner, name = repo.split("/")
            out[label].append({
                "provider": "codeberg", "repo": repo, "sha": sha, "label": label,
                "reference": f"{len(states)} contexts: " + ", ".join(f"{x}={states.count(x)}" for x in sorted(set(states))),
                "patch": f"{repo}@{sha[:10]}", "params": {"owner": owner, "repo": name, "ref": sha},
                "web": f"https://codeberg.org/{repo}/commit/{sha}",
            })
    return out["pass"] + out["fail"]


def main() -> int:
    only = set(sys.argv[1:])  # e.g. "gitlab": rebuild only that provider, keep the other rows
    token = os.environ.get("GH_TOKEN")
    if not token and (not only or "github" in only):
        print("set GH_TOKEN (e.g. GH_TOKEN=$(gh auth token)); collection needs more than 60 GitHub calls", file=sys.stderr)
        return 2
    rows: list[dict] = []
    if only and OUT.exists():
        rows = [r for r in map(json.loads, OUT.read_text().splitlines()) if r["provider"] not in only]
    for repo in (GITHUB_REPOS if not only or "github" in only else []):
        got = github(repo, token)
        print(f"github   {repo:28} {sum(r['label']=='pass' for r in got)} pass / {sum(r['label']=='fail' for r in got)} fail")
        rows += got
    for project in (GITLAB_PROJECTS if not only or "gitlab" in only else []):
        got = gitlab(project)
        print(f"gitlab   {project:28} {sum(r['label']=='pass' for r in got)} pass / {sum(r['label']=='fail' for r in got)} fail")
        rows += got
    for repo in (CODEBERG_REPOS if not only or "codeberg" in only else []):
        got = codeberg(repo)
        print(f"codeberg {repo:28} {sum(r['label']=='pass' for r in got)} pass / {sum(r['label']=='fail' for r in got)} fail")
        rows += got
    random.Random(0).shuffle(rows)
    for i, r in enumerate(rows, 1):
        r["id"] = f"cpv-{i:03d}"
    with OUT.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    print(f"wrote {len(rows)} commits ({sum(r['label']=='pass' for r in rows)} pass, "
          f"{sum(r['label']=='fail' for r in rows)} fail) -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
