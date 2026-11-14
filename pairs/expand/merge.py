#!/usr/bin/env python3
"""Merge the drafted batches into pairs/pairs_expand.yaml, and pairs.yaml + that into pairs/pairs_all.yaml.

Answers get the evidence notation rewritten into plain words (prompts keep it: users paste raw CI output).
Commits whose label rests on Dependabot (dynamic) or scheduled runs are dropped.

    python3 pairs/expand/merge.py
"""
import re
from pathlib import Path
import yaml

HERE = Path(__file__).resolve().parent
PAIRS = HERE.parent
# label decided by dynamic/scheduled runs rather than the commit's own CI (see build_set.py)
DROP = {"cpx-057", "cpx-061", "cpx-065", "cpx-089", "cpx-107", "cpx-123", "cpx-140"}
# the 20 pairs the gate's bag-of-words probe separated most easily (probe_rank.py, out of fold); kept in
# set_aside.yaml for a later rewrite instead of training on a style tell
SET_ASIDE = set("cpx-023 cpx-048 cpx-011 cpx-045 cpx-101 cpx-091 cpx-142 cpx-001 cpx-114 cpx-058 cpx-019 "
                "cpx-074 cpx-036 cpx-013 cpx-076 cpx-112 cpx-127 cpx-022 cpx-130 cpx-010".split())
PLAIN = [
    (r"\ballow_failure=True\b", "allow_failure: true"),
    (r"\ballow_failure=False\b", "allow_failure: false"),
    (r"\bjobs= counts jobs\b", "those numbers count jobs"),
    (r"\bjobs=0\b", "zero jobs"),
    (r"\bfailed_jobs\b", "failed jobs"),
    (r"\bsource=(\w+)", r"source: \1"),
    (r"\battempt=(\d+)", r"attempt \1"),
    (r"\bevent=(\w+)", r"event \1"),
    (r"\bstatus=(\w+)", r"status \1"),
]


class Block(yaml.SafeDumper):
    pass


Block.add_representer(str, lambda d, v: d.represent_scalar(
    "tag:yaml.org,2002:str", v, style="|" if "\n" in v and all(l == l.rstrip() for l in v.split("\n")) else None))


def plain(text: str) -> str:
    text = re.sub(r"(\w)-\n(\w)", r"\1-\2", text)  # rejoin words a line wrap split at a hyphen
    for pat, rep in PLAIN:
        text = re.sub(pat, rep, text)
    return text


rows = []
for f in sorted(HERE.glob("draft_*.yaml")):
    for r in yaml.safe_load(f.read_text()):
        if r["ref"] in DROP:
            continue
        r["chosen"], r["rejected"] = plain(r["chosen"]), plain(r["rejected"])
        rows.append({k: r[k] for k in ("prompt", "chosen", "rejected", "source_url", "source_kind", "ref")})
dump = lambda x: yaml.dump(x, Dumper=Block, sort_keys=False, allow_unicode=True, width=10**6)
(HERE / "set_aside.yaml").write_text(dump([r for r in rows if r["ref"] in SET_ASIDE]))
rows = [r for r in rows if r["ref"] not in SET_ASIDE]
(PAIRS / "pairs_expand.yaml").write_text(dump(rows))
base = yaml.safe_load((PAIRS / "pairs.yaml").read_text())
(PAIRS / "pairs_all.yaml").write_text(dump(base + rows))
print(f"{len(rows)} new pairs -> pairs_expand.yaml; {len(base) + len(rows)} total -> pairs_all.yaml")
