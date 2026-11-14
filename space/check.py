#!/usr/bin/env python3
"""Check a deployed executor the way a validator's remote check will: identity echo, then a full-size batch.

    python3 space/check.py https://<user>-<space>.hf.space/gradio_api/score [N]

POST only reaches the Space under /gradio_api/ (Hugging Face's proxy answers 405 elsewhere).

N texts of 512 tokens (default 30, the most the remote check sends) in one request, timed; the remote check
allows 30 minutes. Pass N=2 for a quick identity-only check.
"""
import json, sys, time, urllib.request

url, n = sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 30
cfg = json.load(open(__file__.rsplit("/", 1)[0] + "/config.json"))
text = [50281] + [1000 + i for i in range(510)] + [50282]  # [CLS] ... [SEP], 512 tokens
body = {"batch": [{"tokens": text}] * n, "foundation_hash": "x", "adapter_hash": "x", "tokenizer_hash": "x"}
t = time.time()
req = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json"})
with urllib.request.urlopen(req, timeout=1800) as r:
    out = json.load(r)
print(f"{len(out['results'])} scores in {time.time() - t:.0f}s; errors: {[x for x in out['results'] if 'error' in x]}")
print("adapter_hash   ", out.get("adapter_hash"))
print("foundation_hash", out.get("foundation_hash"))
print("tokenizer_hash ", out.get("tokenizer_hash"))
assert out.get("foundation_hash") == "0a49b325304bb4cf292e683929689d0457966be264f60bfc94d0072b614bf8e6"
assert out.get("tokenizer_hash") == "67bc76f8b9386efba1a761c1c8e5ad439fd0eaf1c2826e9dd1a205c7af4dc456"
print("identity OK; compare adapter_hash with the keccak256 prepare.sh printed")
