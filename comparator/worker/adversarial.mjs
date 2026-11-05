// node adversarial.mjs [url]
// Adversarial inputs for the comparator's runnable endpoint. Without a URL it drives the
// local handler with the real .wasm; with a URL it calls the deployed endpoint.
import { readFileSync } from "node:fs";
import { makeHandler } from "./handler.js";

const target = process.argv[2];
let send;
if (target) {
  send = async (body) => fetch(target, { method: "POST", headers: { "content-type": "application/json" }, body });
} else {
  const bin = readFileSync(new URL("../CODE_PATCH_VERIFY-comparator.wasm", import.meta.url));
  const handle = makeHandler((await WebAssembly.instantiate(bin, {})).instance.exports);
  send = (body) => handle(new Request("http://local/", { method: "POST", body }));
}

const q = (t, m, s) => `{"ground_truth_value":${t},"miner_value":${m},"spec":${s}}`;
const cases = [
  // [name, raw body, check(status, json)]
  ["malformed JSON is a 400", "{not json", (s) => s === 400],
  ["missing batch is a 400", '{"items":[]}', (s) => s === 400],
  ["empty batch gives empty results", '{"batch":[]}', (s, j) => s === 200 && j.results.length === 0],
  ["pass/fail: right answer scores 10000", `{"batch":[${q(1, 1, "[3,0]")}]}`, (s, j) => j.results[0].score === 10000],
  ["pass/fail: wrong answer scores 0", `{"batch":[${q(1, 0, "[3,0]")}]}`, (s, j) => j.results[0].score === 0],
  ["pass/fail: out-of-domain answer 2 scores 0", `{"batch":[${q(1, 2, "[3,0]")}]}`, (s, j) => j.results[0].score === 0],
  ["truth 0 is refused, not scored", `{"batch":[${q(0, 0, "[3,0]")}]}`, (s, j) => "error" in j.results[0]],
  ["boolean value is refused", `{"batch":[${q("true", 1, "[3,0]")}]}`, (s, j) => "error" in j.results[0]],
  ["float value is refused", `{"batch":[${q(1.5, 1, "[0,0]")}]}`, (s, j) => "error" in j.results[0]],
  ["hex string is refused", `{"batch":[${q('"0x10"', 16, "[0,0]")}]}`, (s, j) => "error" in j.results[0]],
  ["null value is refused", `{"batch":[${q("null", 1, "[0,0]")}]}`, (s, j) => "error" in j.results[0]],
  ["value above int64 is refused", `{"batch":[${q("9223372036854775808", 1, "[0,0]")}]}`, (s, j) => "error" in j.results[0]],
  ["value below int64 is refused", `{"batch":[${q("-9223372036854775809", 1, "[0,0]")}]}`, (s, j) => "error" in j.results[0]],
  ["int64 max is scored exactly", `{"batch":[${q("9223372036854775807", "9223372036854775807", "[0,0]")}]}`, (s, j) => j.results[0].score === 10000],
  ["spec of wrong length is refused", `{"batch":[${q(5, 5, "[0]")}]}`, (s, j) => "error" in j.results[0]],
  ["missing spec is refused", '{"batch":[{"ground_truth_value":5,"miner_value":5}]}', (s, j) => "error" in j.results[0]],
  ["one bad item does not spoil the batch", `{"batch":[${q(1, 1, "[3,0]")},${q("true", 1, "[3,0]")},${q(1000, 1050, "[1,100]")}]}`,
    (s, j) => j.results.length === 3 && j.results[0].score === 10000 && "error" in j.results[1] && j.results[2].score === 7500],
  ["100-question batch answered in order", `{"batch":[${Array.from({ length: 100 }, (_, i) => q(i + 1, i + 1, "[0,0]")).join(",")}]}`,
    (s, j) => j.results.length === 100 && j.results.every((r) => r.score === 10000)],
];

let failed = 0;
for (const [name, body, check] of cases) {
  const res = await send(body);
  let json = null;
  try { json = await res.json(); } catch {}
  const ok = (() => { try { return check(res.status, json); } catch { return false; } })();
  if (!ok) failed++;
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${ok ? "" : `  -> ${res.status} ${JSON.stringify(json)?.slice(0, 120)}`}`);
}
console.log(`\n${cases.length - failed}/${cases.length} passed${target ? ` against ${target}` : " (local handler)"}`);
process.exit(failed ? 1 : 0);
