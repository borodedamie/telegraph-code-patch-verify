#!/usr/bin/env python3
"""Flag numbers and short shas in drafted pairs that do not appear in that commit's CI record.

    python3 pairs/expand/check_facts.py pairs/expand/draft_*.yaml

ponytail: a number/sha check catches invented counts and ids, not wrong reasoning; read the flagged rows
and a sample of the rest by hand.
"""
import json, re, sys
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[2]
ev = {e["id"]: e for e in map(json.loads, (ROOT / "pairs/expand_evidence.jsonl").read_text().splitlines())}
NUM = re.compile(r"(?<![\w.])\d+(?:\.\d+)*(?![\w.])")
SHA = re.compile(r"\b[0-9a-f]{7,40}\b")
# small counts the writer may derive (e.g. "two workflows", "3 of 5"), checked by eye instead
OK_SMALL = {str(i) for i in range(0, 13)}

bad = 0
rows = 0
for path in sys.argv[1:]:
    for r in yaml.safe_load(open(path)):
        rows += 1
        e = ev.get(r["ref"])
        if e is None:
            print(f"{path}: {r['ref']}: unknown ref"); bad += 1; continue
        jobs = e.get("jobs") or []
        sums = [len(jobs)] + [sum(j["status"] == s for j in jobs) for s in {j["status"] for j in jobs}]
        sums += [sum(w["jobs"] for w in e.get("workflows") or [])]  # GitHub job total across workflows
        record = json.dumps(e) + " " + " ".join(map(str, sums))
        issues = []
        if r.get("source_url") != e["web"]:
            issues.append("source_url mismatch")
        for field in ("prompt", "chosen", "rejected"):
            text = r[field]
            for n in NUM.findall(text):
                if n not in OK_SMALL and n not in record:
                    issues.append(f"{field}: number {n} not in record")
            for s in SHA.findall(text):
                if any(c.isalpha() for c in s) and not e["sha"].startswith(s):
                    issues.append(f"{field}: sha {s} is not this commit")
        if issues:
            bad += 1
            print(f"{Path(path).name}: {r['ref']} ({e['label']}): " + "; ".join(sorted(set(issues))))
print(f"{rows} pairs checked, {bad} flagged")
