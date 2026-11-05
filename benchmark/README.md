# CODE_PATCH_VERIFY truth-source benchmark

Checks that the three truth sources in `../truth_sources/` return the correct CI verdict
for finished public commits.

## Method

Each commit's reference label comes from a different record than the one its truth source
reads, so agreement is evidence, not an echo.

| Provider | Reference label from | Truth source reads |
|---|---|---|
| GitHub | Actions workflow runs for the commit | check suites for the commit |
| GitLab | the CI pipeline's jobs (push and merge-request pipelines only) | the commit's pipeline status |
| Codeberg | latest status per context | combined status |

Only settled commits are kept. Commits with runs still in progress, cancelled runs, or
conflicting records are excluded. Sets are balanced between passing and failing commits.

## Results (2026-11-05)

| Set | Repos | Commits | Correct | GitHub calls |
|---|---|---|---|---|
| Development (`benchmark.jsonl`) | 6 GitHub, 3 GitLab, 1 Codeberg | 120 (60 pass, 60 fail) | 120 | with token |
| Held-out (`holdout.jsonl`) | 5 GitHub, 2 GitLab, 2 Codeberg, none reused | 72 (36 pass, 36 fail) | 72 | keyless |

Per-commit results are in `results/`.

## What the development set changed

The first version of the GitHub source read check runs. It scored 62 of 72 on GitHub
commits, with 10 failing commits reported as passing. In those commits, workflows failed
before starting any job, leaving a failed check suite but no check run. The source now
reads check suites, which record those failures.

The first GitLab reference labels also counted GitLab Duo agent pipelines
(`source: duo_workflow`), which are not the commit's CI. The reference now uses push and
merge-request pipelines only.

The held-out set was built and scored once after these changes, with nothing adjusted.

## Limitations

- On the network a parser model reads each raw answer. This benchmark applies the verdict
  rule in code, so it shows each source carries the right answer, not how the parser reads it.
- GitHub allows 60 keyless requests per hour per IP.
- A re-run of CI can change a commit's result after the benchmark was built.
- GitHub returns at most 100 check suites per call. No benchmark commit came close.

## Reproduce

```bash
GH_TOKEN=$(gh auth token) python work/benchmark/build_set.py              # development set
HOLDOUT=1 GH_TOKEN=$(gh auth token) python work/benchmark/build_set.py    # held-out set
python work/benchmark/run_truth_sources.py work/benchmark/holdout.jsonl  # keyless scoring
```
