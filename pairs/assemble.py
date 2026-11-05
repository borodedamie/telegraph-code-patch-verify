#!/usr/bin/env python3
"""Combine the draft pair files, attach each commit's URL, and write pairs/pairs.yaml.

source_kind is "llm": the answers were drafted with an AI assistant from the verified CI
records in evidence.jsonl. Change it only for rows a person has rewritten and checked.
"""
import json
from pathlib import Path

import yaml

HERE = Path(__file__).parent
ev = {e["id"]: e for e in map(json.loads, (HERE / "evidence.jsonl").read_text().splitlines())}
over = yaml.safe_load((HERE / "rebalance.yaml").read_text()) or {}
over_c = yaml.safe_load((HERE / "rebalance_chosen.yaml").read_text()) or {}
rows = []
for f in ("draft_interpretation.yaml", "draft_plain.yaml"):
    for r in yaml.safe_load((HERE / f).read_text()):
        rows.append({"prompt": r["prompt"], "chosen": over_c.get(r["ref"], r["chosen"]), "rejected": over.get(r["ref"], r["rejected"]),
                     "source_url": ev[r["ref"]]["web"], "source_kind": "llm", "ref": r["ref"]})
(HERE / "pairs.yaml").write_text(yaml.safe_dump(rows, sort_keys=False, allow_unicode=True, width=1000))
print(f"{len(rows)} pairs -> pairs/pairs.yaml")
