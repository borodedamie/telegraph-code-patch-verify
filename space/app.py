"""CODE_PATCH_VERIFY evaluator executor, as a Hugging Face Gradio Space.

At startup it downloads, and checks by sha256 before use:
  - the shared Foundation Model and engine from the official telegraph-foundation release (hashes pinned below);
  - the adapter package and the kit's executor binary (cmd/adapterexec) from the adapter Worker (config.json).
Then it runs the executor on 127.0.0.1:8088 and forwards every POST to it unchanged. Validators POST the
batch request to the Space URL (the wasmRunnableUrl); GET shows a small status page.
"""
import hashlib
import json
import os
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path

import gradio as gr
import httpx
from fastapi import Request, Response

try:  # ZeroGPU hardware refuses to start without one @spaces.GPU function; the executor is CPU-only
    import spaces

    @spaces.GPU
    def _unused_gpu_hook():
        pass
except ImportError:
    pass

HERE = Path(__file__).resolve().parent
CFG = json.loads((HERE / "config.json").read_text())
DATA = Path(os.environ.get("CPV_DATA", "/tmp/cpv"))
RELEASE = "https://github.com/telegraphprotocol/telegraph-foundation/releases/download/modernbert-base-lora16-v1/"
# from the kit README ("Current foundation and tokenizer")
FOUNDATION_SHA256 = "0a49b325304bb4cf292e683929689d0457966be264f60bfc94d0072b614bf8e6"
ENGINE_SHA256 = "77643d6e1176ab8744801cef93ccb844d0136ed32b8daa865d541f37d13292de"
EXEC = "http://127.0.0.1:8088/"


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(url: str, want: str, name: str) -> Path:
    """Download url to DATA/name unless a copy with the right sha256 is already there; refuse any other bytes."""
    p = DATA / name
    if p.exists() and sha256(p) == want:
        return p
    part = p.with_suffix(p.suffix + ".part")
    # Cloudflare answers 403 to Python's default "Python-urllib" user agent
    req = urllib.request.Request(url, headers={"User-Agent": "cpv-evaluator-space/1.0"})
    with urllib.request.urlopen(req, timeout=600) as r, open(part, "wb") as f:
        shutil.copyfileobj(r, f, 1 << 20)
    got = sha256(part)
    if got != want:
        part.unlink()
        raise SystemExit(f"{url}: sha256 {got}, expected {want}")
    part.rename(p)
    return p


DATA.mkdir(parents=True, exist_ok=True)
onnx = fetch(RELEASE + "foundation_lora_fp32.onnx", FOUNDATION_SHA256, "foundation_lora_fp32.onnx")
engine = fetch(RELEASE + "foundation_engine.wasm", ENGINE_SHA256, "foundation_engine.wasm")
package = fetch(CFG["base_url"] + "/CODE_PATCH_VERIFY.safetensors", CFG["adapter_sha256"], "CODE_PATCH_VERIFY.safetensors")
binary = fetch(CFG["base_url"] + "/adapterexec-linux-amd64", CFG["executor_sha256"], "adapterexec")
binary.chmod(0o755)

proc = subprocess.Popen(
    [str(binary), "--package", str(package), "--listen", "127.0.0.1:8088"],
    env={**os.environ, "FOUNDATION_MODEL_PATH": str(onnx), "FOUNDATION_MODEL_HASH": FOUNDATION_SHA256,
         "FOUNDATION_ENGINE_WASM_PATH": str(engine), "FOUNDATION_ENGINE_WASM_HASH": ENGINE_SHA256})
for _ in range(300):  # the executor loads the foundation before it listens
    try:
        httpx.post(EXEC, content=b"{}", timeout=5)
        break
    except httpx.TransportError:
        if proc.poll() is not None:
            raise SystemExit(f"executor exited with {proc.returncode}")
        time.sleep(1)

client = httpx.AsyncClient(timeout=None)  # a full batch takes minutes; the validator sets the budget


async def score(request: Request) -> Response:
    r = await client.post(EXEC, content=await request.body(), headers={"Content-Type": "application/json"})
    return Response(r.content, status_code=r.status_code, media_type="application/json")


with gr.Blocks(title="CODE_PATCH_VERIFY evaluator") as demo:
    gr.Markdown(
        "# CODE_PATCH_VERIFY evaluator executor\n\n"
        "Runs the Telegraph kit's reference executor (`cmd/adapterexec`) on the shared Foundation Model "
        "with the CODE_PATCH_VERIFY adapter. Validators POST batch requests to this Space's URL.\n\n"
        f"- adapter package sha256: `{CFG['adapter_sha256']}`\n"
        f"- foundation sha256: `{FOUNDATION_SHA256}`\n"
        f"- executor running: `{proc.poll() is None}`")

# Launch through Gradio (ZeroGPU only detects @spaces.GPU functions on launch()), then add the batch route.
# Starlette tries routes in order, so these POST routes only catch paths Gradio's own routes do not.
app, _, _ = demo.launch(server_name="0.0.0.0", server_port=int(os.environ.get("PORT", 7860)),
                        prevent_thread_lock=True)
app.add_api_route("/", score, methods=["POST"])
app.add_api_route("/{path:path}", score, methods=["POST"])
demo.block_thread()
