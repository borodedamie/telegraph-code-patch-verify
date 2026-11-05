# CODE_PATCH_VERIFY: truth sources, comparator and benchmark

Evaluation work for the Telegraph intent `CODE_PATCH_VERIFY_GENERAL`: given a patch, commit or
CI run, did its build and tests pass? Built for the Telegraph Season II hackathon (Evaluators
track) and bounty [telegraphprotocol/bounties#110](https://github.com/telegraphprotocol/bounties/issues/110).
All results are from the Telegraph testnet (Ethereum Sepolia) and public repositories.

## What is here

| Part | What it does | Status |
|---|---|---|
| [`truth_sources/`](truth_sources/) | Three keyless public APIs that report a commit's CI verdict: GitHub check suites, GitLab commit pipeline status, Codeberg combined status | Uploaded; all 3 eligible and in the active snapshot from epoch 2014 |
| [`comparator/`](comparator/) | The comparator module (Rust, `wasm32-unknown-unknown`) and its runnable endpoint (Cloudflare Worker) | Registered as #148; pending (see Status) |
| [`benchmark/`](benchmark/) | Finished public commits with known CI verdicts, and the scripts that score truth sources and miners against them | Results below |

## Results

| Measure | Result |
|---|---|
| Truth sources, development set (120 commits, 10 repos, 3 hosts) | 120 of 120 correct |
| Truth sources, held-out set (72 commits, 9 different repos), called keyless | 72 of 72 correct |
| Comparator against the reference rule, through the node's own runner | 230,134 cases, 0 mismatches |
| Comparator endpoint, adversarial inputs | 18 of 18 handled correctly |
| Registered miners on the same 48-commit sample | best real miner 59% of answered questions; current top three give a constant answer (50%); 12 of 20 answered nothing |

Details: [benchmark/README.md](benchmark/README.md) (method and validity),
[benchmark/MINERS.md](benchmark/MINERS.md) (every miner scored, with reasons),
[benchmark/ROBUSTNESS.md](benchmark/ROBUSTNESS.md) (pending commits, re-runs, rate limits,
cross-host answers, adversarial inputs).

Two flaws were found and fixed along the way. A GitHub source built on check runs missed
workflows that failed before starting any job, scoring 62 of 72 GitHub commits, so the source
now reads check suites. The comparator endpoint's first version coerced booleans and wrapped
out-of-range integers, so it now accepts only in-range integers.

## Comparator module

- File: `comparator/CODE_PATCH_VERIFY-comparator.wasm`, 2,220 bytes, no imports.
- keccak256: `0xf7d79d45b32d5576bf7c9748733d92c620dc272159092642f428884b9081b675`
- Hosted: https://cpv-comparator.clientservices-907.workers.dev/CODE_PATCH_VERIFY-comparator.wasm
- Runnable URL: https://cpv-comparator.clientservices-907.workers.dev
- Registration: #148 on family `CODE_PATCH_VERIFY`

Rebuild it byte for byte (the toolchain is pinned to rustc 1.96.0):

```bash
cd comparator
cargo build --release --target wasm32-unknown-unknown
shasum -a 256 target/wasm32-unknown-unknown/release/cpv_comparator.wasm
# 24eab4bcaee10cb08c233dd39841b78cb2f441d9d53d3ffea9f08c18a4e16d2f
```

Test the endpoint logic with the real module (Node.js 18+):

```bash
cd comparator/worker
node check.mjs           # 3,000 reference cases
node adversarial.mjs     # 18 adversarial cases; pass a URL to test a deployed endpoint
```

`comparator/check_test.go` runs the module through the node's deterministic runner against
`ReferenceScore`. It imports packages from
[telegraph-wasm-baseline](https://github.com/telegraphprotocol/telegraph-wasm-baseline), so copy
the `comparator/` folder into that repository's `work/` directory and run
`go test ./work/comparator/ -v`.

## Reproduce the benchmark

Python 3.10+ with PyYAML, and the GitHub CLI for a token when building sets.

```bash
GH_TOKEN=$(gh auth token) python benchmark/build_set.py              # development set
HOLDOUT=1 GH_TOKEN=$(gh auth token) python benchmark/build_set.py    # held-out set
python benchmark/run_truth_sources.py benchmark/holdout.jsonl        # keyless scoring
GH_TOKEN=$(gh auth token) python benchmark/score_miners.py           # registered miners
GH_TOKEN=$(gh auth token) python benchmark/robustness.py             # robustness checks
```

Rebuilding the sets picks the latest commits, so a rebuild gives a new set rather than the
committed one. The committed `benchmark.jsonl` and `holdout.jsonl` are the sets reported above.

## Status (2026-11-05)

Registration #148 is pending with "only 0 usable public pairs for CODE_PATCH_VERIFY (need 10)".
The Issue describes the intent as deterministic with a comparator, but the node currently lists
`CODE_PATCH_VERIFY` and `CODE_PATCH_VERIFY_GENERAL` as class `judgment`, served by the generic
fallback. This has been raised with the maintainer.

## Limitations

- On the network a parser model reads each truth source's raw answer. The benchmark applies the
  verdict rule in code, so it shows each source carries the right answer, not how the parser reads it.
- Miners were called directly from their registered YAML, not through Telegraph routing, with
  parameters filled as generously as possible. Availability reflects the time of the run.
- GitHub allows 60 keyless requests per hour per IP, and GitLab also rate-limits keyless calls.
- A later re-run of CI can change a commit's verdict after a set was built.
