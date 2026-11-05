# Robustness of the CODE_PATCH_VERIFY truth sources and comparator

Run on 2026-11-04 against live GitHub, GitLab and Codeberg data. Code: `robustness.py`
(truth sources) and `../comparator/worker/adversarial.mjs` (comparator endpoint).
Raw results: `results/robustness.json`.

## Truth sources

| Check | Result | What it shows |
|---|---|---|
| Commits whose CI is still running | 8 of 8 gave no verdict | 2 GitHub, 4 GitLab, 2 Codeberg. A source never guesses before CI finishes. |
| Re-run CI | 8 of 8 reported the latest attempt | A re-run replaces the earlier result. All 8 came from one repo (honojs/hono) and one pattern: a first attempt awaiting approval, then a re-run. |
| Unknown commit, unknown project | no verdict (HTTP 422, HTTP 404) | A bad reference fails the source for that round instead of producing an answer. |
| Rate-limit reply | no verdict | GitHub allows 60 keyless calls per hour per IP. GitLab also rate-limited keyless calls during the run (54 HTTP 429 replies). Both fail the source for that round. |
| Each source asked about the other hosts' commits | 384 calls, 0 verdicts | 330 returned 404 because the repository is not on that host; 54 were rate-limited. A source cannot contradict another by answering for a commit it does not host. |

The network takes the median of up to three sampled sources. Because a source only answers for
commits on its own host, and gives no verdict for unfinished or unknown commits, the sources that
do answer a question report the same CI record.

## Comparator endpoint

`adversarial.mjs` sends 18 hostile or edge-case requests to the runnable endpoint.

| Area | Cases |
|---|---|
| Malformed requests | invalid JSON and a missing batch return 400; an empty batch returns no results |
| Pass/fail scoring | the right answer scores 10000; a wrong answer and an out-of-domain answer (2) score 0 |
| Refused inputs | zero truth, booleans, floats, hex strings, null, values above or below the int64 range, a spec of the wrong length, a missing spec |
| Exact extremes | int64 max is scored exactly |
| Batches | one bad item does not spoil the rest; a 100-question batch is answered in order |

The first version of the endpoint failed 6 of the 18. It coerced booleans and hex strings to
numbers, wrapped out-of-range integers, and rejected a whole batch because of one float. The
handler now accepts only whole numbers within the int64 range and refuses anything else per item.
It passes 18 of 18, and the 3,000-case reference check still shows 0 mismatches.

The fix changed only the endpoint's request handling. The registered module
(keccak256 0xf7d79d45...b675, registration 148) is unchanged.

## Limitations

- Re-run coverage is narrow: one repository and one re-run pattern.
- Rate limits depend on the calling IP; a busy validator could hit them sooner than this test did.
- On the network a parser model reads each source's raw answer; these checks apply the verdict rule in code.
