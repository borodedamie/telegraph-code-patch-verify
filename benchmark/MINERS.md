# CODE_PATCH_VERIFY miners scored against the benchmark

Run on 2026-11-05. Sample: 48 commits from the development and held-out sets (24 GitHub, 12 GitLab, 12 Codeberg; half passing, half failing). Each miner was called exactly as its registered YAML declares, with parameters filled from the commit as generously as possible. A response with no CI verdict counts as wrong. Method and code: `score_miners.py`; per-commit results: `results/miners.json`.

| Miner | Network rank | Network score | Correct | Answered | Accuracy when answered | Why |
|---|---|---|---|---|---|---|
| **This work: the three truth sources** | - | - | **48/48** | 48/48 | 100% | Commit-aware; reads check suites, pipeline status, combined status |
| patch-circleci-recent | 1 | 0.9918 | 24/48 | 48/48 | 50% | Reads one fixed CircleCI project's latest build, whatever commit is asked; same answer every time |
| patch-godbolt | 3 | 0.6598 | 24/48 | 48/48 | 50% | Runs a fixed code snippet in a sandbox; exits cleanly every time |
| patch-judge0-ce | 2 | 0.7909 | 24/48 | 48/48 | 50% | Runs a fixed code snippet in a sandbox; exits cleanly every time |
| patch-wandbox | 16 | 0 | 24/48 | 48/48 | 50% | Runs a fixed code snippet in a sandbox; exits cleanly every time |
| patch-gh-commit-check | 7 | 0 | 18/48 | 38/48 | 47% | Checks the main branch, never the commit asked; repos whose branch is master return HTTP 422 |
| patch-gh-actions-requests-tests | 5 | 0 | 13/48 | 26/48 | 50% | Hard-wired to psf/requests' run-tests.yml; 404 elsewhere |
| zk-patchproof | - | - | 13/48 | 22/48 | 59% | Commit-aware and GitHub-only; often hit its own upstream GitHub rate limit; reads an all-skipped aggregate as not passed |
| zk-code-ci | - | - | 2/48 | 4/48 | 50% | Judges one Actions run URL, not a commit; not comparable on commit-level questions |
| chainsight-oracle | - | - | 0/48 | 0/48 | - | Price/finance endpoints; no CI result |
| codewire-code-patch-verify | - | - | 0/48 | 0/48 | - | Its language model was unavailable for every call |
| patch-gh-commit | 6 | 0 | 0/48 | 0/48 | - | Returns commit metadata; no CI result |
| patch-gh-commits-list | 8 | 0 | 0/48 | 0/48 | - | Returns a commit list; no CI result |
| patch-gh-compare | 9 | 0 | 0/48 | 0/48 | - | Returns a diff; no CI result |
| patch-gh-compare-react | 10 | 0 | 0/48 | 0/48 | - | Returns a diff; no CI result |
| patch-gh-pr-files | 11 | 0 | 0/48 | 0/48 | - | Returns PR files; no CI result |
| patch-gitlab-compare | 12 | 0 | 0/48 | 0/48 | - | Returns a diff; no CI result |
| patch-gitlab-pipeline | 13 | 0 | 0/48 | 0/48 | - | Unencoded project path in its URL; every call returns 404 |
| patch-npm-pkg | 14 | 0 | 0/48 | 0/48 | - | Returns npm package metadata; no CI result |
| patch-npm-react | 15 | 0 | 0/48 | 0/48 | - | Returns npm package metadata; no CI result |
| telegraph-verity-intelligence | - | - | 0/48 | 0/48 | - | Registered endpoint returns 404 |

## Findings

- **The current top three miners are coin flips.** CircleCI (rank 1, score 0.99), Judge0 (rank 2, 0.79) and Godbolt (rank 3, 0.66) give the same answer for every commit, so they score 50% on a balanced benchmark. The network's scores date from the judgment era (last scored epoch 1996).
- **Twelve miners answered none of the 48 questions.** Nine return commit metadata, diffs, PR files, package metadata or prices instead of a CI result. Two returned errors (a 404, an unavailable model). One is mis-configured (below).
- **Two miners are mis-configured.** patch-gh-commit-check checks `main` instead of the commit and fails on `master` repos. patch-gitlab-pipeline's URL returns 404 on every call.
- **The only commit-aware miner is zk-patchproof.** It is GitHub-only and was often rate-limited by GitHub during the run.
- **The truth sources separate these cases.** They answered all 48 commits correctly, so a miner's score under them reflects whether it reads the commit's real CI result.

## Limitations

- On the network a parser model reads each answer; here one generous rule reads them all (`verdict()` in `score_miners.py`).
- Third-party miners were called directly, not through Telegraph routing. Availability reflects the time of the run.
- zk-code-ci accepts an Actions run URL; it was given each commit's latest run, which is not always the run that decides the commit.
