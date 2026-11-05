import wasm from "../CODE_PATCH_VERIFY-comparator.wasm";
import { makeHandler } from "./handler.js";

const handle = makeHandler(new WebAssembly.Instance(wasm, {}).exports);

export default { fetch: (request) => handle(request) };
