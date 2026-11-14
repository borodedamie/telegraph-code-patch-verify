# Drafting spec: CODE_PATCH_VERIFY_GENERAL preference pairs

The intent: a user asks whether a code patch (a commit) passed CI. A good answer gives the right verdict and
backs it with the commit's actual CI record. We are training an evaluator to prefer the better answer.

## Facts: the only source of truth

Use ONLY the evidence file you are given. Never invent job names, counts, authors, diffs, test names, dates
or causes. Wording limits, because the record does not show more than this:
- GitHub `jobs=N` is how many jobs the workflow had, not how many passed. For a workflow with conclusion
  success, say "succeeded (N jobs)" or "succeeded with its N jobs", never "all N jobs passed" (some may have
  been skipped). `failed_jobs` lists only jobs that failed or timed out; cancelled jobs are not listed.
- A workflow with conclusion failure and jobs=0 failed before starting any job: nothing ran. That is a FAIL.
- A workflow with conclusion cancelled is not a pass. Skipped workflows on a passing commit are not failures.
- attempt=2 or more means the workflow was re-run; the record shows only the latest attempt's result.
- The same workflow name listed twice usually means separate triggers (for example pull_request and push, or
  pull_request_target, or a branch and a tag); do not claim which unless the event field shows it.
- GitLab: a failed job with allow_failure=True does not fail the pipeline. A failed job with allow_failure=False
  does. manual jobs never ran and are not required. Only non-success jobs are listed; the counts line has totals.
- Codeberg: each context's latest status; any failure makes the commit fail.
- LABEL is the settled verdict. The better answer must agree with it.

## What to write

For each commit you choose, write ONE pair. Skip a commit if its record is confusing or you cannot write a
clear, true better answer. Aim for 26-30 pairs from your file. Mix two kinds, about 60/40:

1. **interpretation**: the prompt includes the CI record (paraphrased, in the user's words, with the
   relevant workflow/job names and conclusions). The question asks for a verdict. Favour commits whose record
   has a trap: allowed failures, manual jobs, zero-job failures, cancelled runs, skipped workflows on a pass,
   re-runs, duplicate workflow names, mostly-green-but-failed, lint/meta-only failures, many Codeberg contexts.
2. **plain**: the prompt only names the commit (repo + short sha, maybe the message), the way a user types it.
   The better answer gives the verdict with evidence from the record.

Prompt voice: vary it. Some formal, some casual, some terse ("pass or fail?"), some with small typos or
lowercase. 16-600 characters. Do not start many prompts the same way. Never copy a prompt's structure
verbatim from one pair to the next.

## The worse answer (rejected)

It must be clearly wrong or clearly weaker for a reason an expert can name, but believable. Use the
failure modes real miners showed, and vary them:
- misreads the record: zero-job failure read as "nothing failed"; allowed failure read as a red pipeline;
  manual or skipped jobs read as failures; a re-run read as a hidden failure (or a repeated failure read as
  a flake); cancelled read as success; "most workflows passed" read as a pass; lint/meta failure dismissed.
- checks the wrong thing: the default branch's latest run, another pipeline, the PR's merge state.
- reasons from the commit message or the diff instead of CI ("the title says it fixes it", "docs-only
  change cannot fail").
- reports a sandbox/local run exit code instead of the CI record.
- non-answer: "cannot be determined", metadata only, "pending" when it is settled.
Keep the worse answer's facts about the record accurate where it states them; the error is in the reasoning
or the thing it checked. Flip the verdict direction in roughly half the pairs (a wrong "pass" for failing
commits, a wrong "fail" for passing ones), and sometimes keep the right verdict but with wrong reasoning or a
false supporting claim.

## Style balance (an automated gate checks this)

- chosen and rejected: 120-480 characters each, similar length; make the rejected answer the LONGER one in
  about half of the pairs.
- Both answers use the same concrete vocabulary (the same workflow/job names, numbers). The better answer
  must not be identifiable by words like "actually", "correctly", or by always starting "No."/"Yes.".
- Vary verdict openers: "Passed.", "No.", "Yes.", "Failed.", "It failed", "Green.", "Not passing.",
  "CI is red", "This one passed", or no opener at all. Do not reuse one sentence pattern repeatedly.
- No markdown, no bullet lists inside answers. Plain sentences.

## Output

Write a YAML list to the output path you are given, each item exactly:

```yaml
- ref: cpx-NNN
  kind: interpretation   # or plain
  prompt: |
    ...
  chosen: |
    ...
  rejected: |
    ...
  source_url: <the commit's web URL from the evidence>
  source_kind: llm
```

Use `|` block scalars for prompt/chosen/rejected, 4-space indented, lines wrapped at about 110 characters.
Validate it parses: `python3 -c "import yaml; d=yaml.safe_load(open('<path>')); print(len(d))"`.
