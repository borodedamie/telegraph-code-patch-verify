#!/usr/bin/env python3
"""Rank pairs by how easily the kit's bag-of-words probe separates chosen from rejected (out of fold).

    PYTHONPATH=<telegraph-wasm-baseline> python pairs/expand/probe_rank.py [N]
"""
import json, random, sys
from collections import Counter
from pathlib import Path
import numpy as np
import yaml
from float_runtime.train_adapter import _tokens

PAIRS = Path(__file__).resolve().parents[1]
rows = [json.loads(l) for l in (PAIRS / "pairs_all.jsonl").read_text().splitlines()]
refs = [r["ref"] for r in yaml.safe_load((PAIRS / "pairs_all.yaml").read_text())]


def fit(tr):
    """The gate's probe (train_adapter._surface_probe_acc), returning its scoring function and weights."""
    df = Counter()
    for r in tr:
        for s in ("chosen", "rejected"):
            df.update(set(_tokens(r[s])))
    vocab = {w: i for i, (w, _) in enumerate(df.most_common(4000))}
    d = len(vocab)

    def vec(ts):
        m = np.zeros((len(ts), d), np.float32)
        for i, t in enumerate(ts):
            for w in _tokens(t):
                if w in vocab:
                    m[i, vocab[w]] += 1
        return m / np.maximum(np.linalg.norm(m, axis=1, keepdims=True), 1e-8)

    x = vec([r["chosen"] for r in tr] + [r["rejected"] for r in tr])
    y = np.r_[np.ones(len(tr)), np.zeros(len(tr))]
    w, b, rng = np.zeros(d, np.float32), 0.0, np.random.default_rng(0)
    for _ in range(60):
        o = rng.permutation(len(x))
        for s in range(0, len(o), 64):
            sl = o[s:s + 64]
            p = 1 / (1 + np.exp(-(x[sl] @ w + b)))
            g = (p - y[sl]) / len(sl)
            w -= 0.5 * (x[sl].T @ g + 1e-4 * w)
            b -= 0.5 * g.sum()
    return (lambda t: float(vec([t])[0] @ w + b)), w, vocab, df


idx = list(range(len(rows)))
random.Random(0).shuffle(idx)
margin = {}
for k in range(5):
    ev = set(idx[k::5])
    f, *_ = fit([rows[i] for i in idx if i not in ev])
    for i in ev:
        margin[i] = f(rows[i]["chosen"]) - f(rows[i]["rejected"])
print(f"out-of-fold pair accuracy {sum(m > 0 for m in margin.values()) / len(margin):.1%}")
_, w, vocab, df = fit(rows)
inv = {i: t for t, i in vocab.items()}
imp = w * np.array([df[inv[i]] for i in range(len(vocab))])
top = np.argsort(imp)
print("chosen features:  ", ", ".join(inv[i] for i in top[-25:][::-1]))
print("rejected features:", ", ".join(inv[i] for i in top[:25]))
n = int(sys.argv[1]) if len(sys.argv) > 1 else 40
print("top tell pairs:", " ".join(refs[i] for i in sorted(margin, key=lambda i: -margin[i])[:n]))
