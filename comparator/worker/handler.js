// Runnable-URL handler for the CODE_PATCH_VERIFY comparator.
// POST {"batch":[{"ground_truth_value":int64,"miner_value":int64,"spec":[code,tolerance]},...]}
// ->  {"results":[{"score":0..10000} | {"error":"..."}, ...]}  (one per question, same order)

// JSON.parse turns integers above 2^53 into rounded floats, and truths reach 1e18,
// so the int64 fields are quoted before parsing and read back with BigInt.
function parseBatch(text) {
  // Only whole integer literals are quoted (a float or exponent is left alone and refused later).
  const quoted = text
    .replace(/("(?:ground_truth_value|miner_value)"\s*:\s*)(-?\d+)(?=\s*[,}])/g, '$1"$2"')
    .replace(/("spec"\s*:\s*\[\s*)(-?\d+)(\s*,\s*)(-?\d+)(\s*\])/g, '$1"$2"$3"$4"$5');
  return JSON.parse(quoted);
}

const I64_MIN = -(2n ** 63n);
const I64_MAX = 2n ** 63n - 1n;

// Strict int64: a decimal integer (quoted by parseBatch) within range. Booleans, floats,
// hex or other strings, null and out-of-range values are refused, never coerced.
function toI64(v, name) {
  if (typeof v !== "string" || !/^-?\d+$/.test(v)) throw new Error(`${name} must be an int64 integer`);
  const n = BigInt(v);
  if (n < I64_MIN || n > I64_MAX) throw new Error(`${name} is outside the int64 range`);
  return n;
}

export function makeHandler(exports) {
  const { imw_score_deterministic: score, imw_alloc: alloc, imw_free: free, memory } = exports;

  function scoreOne(q) {
    const truth = toI64(q?.ground_truth_value, "ground_truth_value");
    const miner = toI64(q?.miner_value, "miner_value");
    if (!Array.isArray(q.spec) || q.spec.length !== 2) throw new Error("spec must be [code, tolerance]");
    const code = toI64(q.spec[0], "spec code");
    const tol = toI64(q.spec[1], "spec tolerance");
    if (truth === 0n) throw new Error("truth value is zero; ground truth was not resolved");
    const ptr = alloc(16);
    if (!ptr) throw new Error("imw_alloc returned a null pointer");
    const view = new DataView(memory.buffer);
    view.setBigInt64(ptr, code, true);
    view.setBigInt64(ptr + 8, tol, true);
    const s = Number(score(truth, miner, ptr));
    free(ptr, 16);
    if (s < 0 || s > 10000) throw new Error(`comparator rejected the input (${s})`);
    return s;
  }

  return async function handle(request) {
    if (request.method === "GET") {
      return Response.json({ ok: true, module: "CODE_PATCH_VERIFY comparator", interface: "POST {batch:[...]}" });
    }
    if (request.method !== "POST") return Response.json({ error: "use POST" }, { status: 405 });
    let body;
    try {
      body = parseBatch(await request.text());
    } catch {
      return Response.json({ error: "body is not valid JSON" }, { status: 400 });
    }
    if (!body || !Array.isArray(body.batch)) return Response.json({ error: "missing batch array" }, { status: 400 });
    if (body.batch.length > 2000) return Response.json({ error: "batch too large" }, { status: 400 });
    const results = body.batch.map((q) => {
      try {
        return { score: scoreOne(q) };
      } catch (e) {
        return { error: String(e?.message ?? e) };
      }
    });
    return Response.json({ results });
  };
}
