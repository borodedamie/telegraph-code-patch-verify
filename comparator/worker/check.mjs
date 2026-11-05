// node check.mjs: drives the endpoint handler with the real .wasm and checks it against the reference fixture.
import { readFileSync } from "node:fs";
import { makeHandler } from "./handler.js";

const bin = readFileSync(new URL("../CODE_PATCH_VERIFY-comparator.wasm", import.meta.url));
const { instance } = await WebAssembly.instantiate(bin, {});
const handle = makeHandler(instance.exports);
const cases = readFileSync(new URL("./fixture.txt", import.meta.url), "utf8").trim().split("\n").map((l) => l.split(" "));

let bad = 0;
for (let i = 0; i < cases.length; i += 100) {
  const chunk = cases.slice(i, i + 100);
  // Raw integer literals, exactly as the node sends them.
  const body = `{"batch":[${chunk.map(([c, t, tr, m]) => `{"ground_truth_value":${tr},"miner_value":${m},"spec":[${c},${t}]}`).join(",")}]}`;
  const res = await (await handle(new Request("http://x/", { method: "POST", body }))).json();
  if (res.results.length !== chunk.length) throw new Error("result count mismatch");
  chunk.forEach(([, , , , want], j) => {
    const got = res.results[j].score;
    if (String(got) !== want) { bad++; if (bad <= 5) console.log("mismatch", chunk[j], res.results[j]); }
  });
}
const bigTruth = await (await handle(new Request("http://x/", { method: "POST",
  body: '{"batch":[{"ground_truth_value":1000000000000000001,"miner_value":1000000000000000000,"spec":[0,0]}]}' }))).json();
console.log(`${cases.length} cases via endpoint, ${bad} mismatches; 1e18+1 vs 1e18 exact match ->`, bigTruth.results[0]);
process.exit(bad || bigTruth.results[0].score !== 0 ? 1 : 0);
