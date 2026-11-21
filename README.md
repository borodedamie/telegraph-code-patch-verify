# CODE_PATCH_VERIFY: evaluator adapter

Evaluation work for the Telegraph intent `CODE_PATCH_VERIFY` (class `judgment`): given a patch,
commit or CI run, did its build and tests pass? Built for the Telegraph Season II hackathon
(Evaluators track) and bounty
[telegraphprotocol/bounties#110](https://github.com/telegraphprotocol/bounties/issues/110).
All results are from the Telegraph testnet (Ethereum Sepolia) and public repositories.

The deliverable is a trained **evaluator adapter** — a LoRA reward model on ModernBERT-base that
ranks the better of two CI-verdict answers. It replaces an earlier deterministic comparator (see
"Comparator (legacy)"), which the node rejected as the wrong class for a `judgment` intent.

## What is here

| Part | What it does | Status |
|---|---|---|
| [`adapter-host/`](adapter-host/) | Cloudflare Worker serving the adapter package (`wasmUrl`) and a static Linux build of the executor | Deployed |
| [`space/`](space/) | Hugging Face Gradio Space running the kit's executor (`wasmRunnableUrl`) | Deployed |
| [`pairs/`](pairs/) | Preference pairs (prompt / better answer / worse answer) used to train and test the adapter | 171 pairs |
| [`truth_sources/`](truth_sources/) | Three keyless public APIs that report a commit's CI verdict: GitHub check suites, GitLab commit pipeline status, Codeberg combined status | Uploaded; all 3 eligible |
| [`benchmark/`](benchmark/) | Finished public commits with known CI verdicts, and the scripts that score truth sources and miners against them | Results below |
| [`comparator/`](comparator/) | The earlier deterministic comparator (Rust WASM), superseded by the adapter | Legacy |

## Adapter module

A LoRA (rank 8, alpha 32) Bradley-Terry reward model fine-tuned on ModernBERT-base
(`modernbert-base-lora16-v1`, foundation hash `0a49b325304bb4cf292e683929689d0457966be264f60bfc94d0072b614bf8e6`).
It scores a (question, answer) pair under the node's fixed template and tokenizer, so the
package is a drop-in `CODE_PATCH_VERIFY` evaluator.

**r6** (current, live):

| Field | Value |
|---|---|
| keccak256 (`wasmHash`) | `0x461b850afa136951ccd10217b8ca713a4de3587f9cb375dbede05dbc3769df85` |
| package sha256 | `3a6440cbceb706e2bc36480b667a586ff8c4637eb759d0658b97e250e0f35d22` |
| `wasmUrl` | `https://cpv-adapter.clientservices-907.workers.dev/CODE_PATCH_VERIFY.safetensors` |
| `wasmRunnableUrl` | `https://borodedamie-cpv-evaluator.hf.space/gradio_api/score` |

Trained on 171 preference pairs (146 train / 25 held-out), r6 scores **92% pairwise accuracy** on
the held-out set, beating the "prefer the longer answer" baseline (56%). The pairs cover
cross-provider CI traps — skipped jobs, zero-job failures, GitLab optional/`allow_failure` jobs,
Codeberg cancelled statuses, coverage-only failures and snapshot-only diffs — across GitHub,
GitLab and Codeberg.

Deployment is scripted in [`adapter-host/prepare.sh`](adapter-host/prepare.sh) and documented in
[`adapter-host/README.md`](adapter-host/README.md):

1. `prepare.sh` copies the package into `adapter-host/public/`, rebuilds the Linux executor and
   writes `space/config.json` with the sha256 of both.
2. `npx wrangler deploy` (in `adapter-host/`) serves the package.
3. Re-upload the four files in `space/` to the Space, then register the keccak256 with the node.

## Validation results

| Measure | Result |
|---|---|
| Truth sources, development set (120 commits, 10 repos, 3 hosts) | 120 of 120 correct |
| Truth sources, held-out set (72 commits, 9 different repos), called keyless | 72 of 72 correct |
| Registered miners on the same 48-commit sample | best real miner 59% of answered questions; current top three give a constant answer (50%); 12 of 20 answered nothing |

Details: [benchmark/README.md](benchmark/README.md) (method and validity),
[benchmark/MINERS.md](benchmark/MINERS.md) (every miner scored, with reasons),
[benchmark/ROBUSTNESS.md](benchmark/ROBUSTNESS.md) (pending commits, re-runs, rate limits,
cross-host answers, adversarial inputs), and [pairs/README.md](pairs/README.md) (how the
training pairs are made).

A GitHub source built on check runs initially missed workflows that failed before starting any
job, scoring 62 of 72 GitHub commits, so the source now reads check suites.

## Comparator (legacy)

The first submission was a deterministic Rust comparator rather than a trained adapter. It
matched the reference rule on 230,134 cases (0 mismatches) and 18 of 18 adversarial inputs, but
the node lists `CODE_PATCH_VERIFY` as class `judgment`, which needs a trained adapter rather
than a deterministic comparator. The adapter above supersedes it.

- File: `comparator/CODE_PATCH_VERIFY-comparator.wasm`, 2,220 bytes, no imports.
- keccak256: `0xf7d79d45b32d5576bf7c9748733d92c620dc272159092642f428884b9081b675`
- Runnable URL: https://cpv-comparator.clientservices-907.workers.dev

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

## Limitations

- On the network a parser model reads each truth source's raw answer. The benchmark applies the
  verdict rule in code, so it shows each source carries the right answer, not how the parser reads it.
- Miners were called directly from their registered YAML, not through Telegraph routing, with
  parameters filled as generously as possible. Availability reflects the time of the run.
- GitHub allows 60 keyless requests per hour per IP, and GitLab also rate-limits keyless calls.
- A later re-run of CI can change a commit's verdict after a set was built.
