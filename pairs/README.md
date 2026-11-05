# Question pairs for CODE_PATCH_VERIFY_GENERAL

57 preference pairs for the judgment intent `CODE_PATCH_VERIFY_GENERAL`, built from the
development set in `../benchmark/benchmark.jsonl`. The held-out set is not used, so it can test
an evaluator adapter later.

## How they are made

1. `collect_evidence.py` fetches the CI record behind each development commit: GitHub workflow
   runs and jobs, GitLab pipeline jobs, Codeberg status contexts. Output: `evidence.jsonl`.
2. Commits whose record changed after the benchmark was built (re-runs, later workflows) are left out.
3. Two kinds of question:
   - **Interpretation** (`draft_interpretation.yaml`, 30 pairs): the prompt includes the CI record.
     The better answer reads it correctly. The worse answer misreads it: counting a workflow that
     failed before starting any job as a pass, treating skipped or manual jobs as failures,
     treating an allowed failure as a red pipeline, or reading a re-run as a hidden failure.
   - **Plain** (`draft_plain.yaml`, 27 pairs): the prompt names a commit the way a user would.
     The better answer gives the verdict with evidence about that commit. The worse answer repeats
     a failure mode measured in `../benchmark/MINERS.md`: checking another branch, returning
     metadata or a diff, a sandbox exit code, or claiming tests passed when none ran.
4. `rebalance.yaml` and `rebalance_chosen.yaml` adjust wording and length so neither answer
   length nor vocabulary gives the better answer away. `assemble.py` combines everything into
   `pairs.yaml`.

## Checks

The telegraph-wasm-baseline dataset gate passes:

| Check | Result | Limit |
|---|---|---|
| Unique worse answers | 100% | at least 80% |
| Largest single worse answer | 1.8% | at most 2% |
| "Pick the longer answer" | 51.7% | at most 65% |
| Bag-of-words probe without the prompt | 61.3% | at most 65% |
| Held-out leakage | 0% | at most 10% |

No two prompts are 75% similar or more; the pool rejects prompts at 85%.

## Provenance

Every pair's facts come from public CI records, linked in `source_url`. The answers were drafted
with an AI assistant, so rows carry `source_kind: llm`. Change that only for rows a person has
rewritten and checked.

## Reproduce

```bash
GH_TOKEN=$(gh auth token) python pairs/collect_evidence.py
python pairs/assemble.py
python <telegraph-wasm-baseline>/work/pairs.py --intent CODE_PATCH_VERIFY_GENERAL \
  --drafts pairs/pairs.yaml --out pairs/pairs.jsonl --check-gate
```
