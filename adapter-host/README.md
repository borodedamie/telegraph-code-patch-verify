# Hosting the CODE_PATCH_VERIFY evaluator adapter

Two URLs go into the registration:

| Registration field | What serves it | URL |
|---|---|---|
| `wasmUrl` | this Worker (static assets, the exact package bytes) | `https://cpv-adapter.<subdomain>.workers.dev/CODE_PATCH_VERIFY.safetensors` |
| `wasmRunnableUrl` | the Gradio Space in `../space`, running the kit's executor | `https://<user>-<space>.hf.space/gradio_api/score` |

The Worker also serves a static Linux build of the kit's executor (`adapterexec-linux-amd64`), which the
Space downloads. The Space checks every file by sha256 before using it and refuses anything else.

## 1. Deploy the Worker

```bash
cd ~/Documents/codes/telegraph-code-patch-verify/adapter-host
npx wrangler login && npx wrangler deploy        # prints https://cpv-adapter.<subdomain>.workers.dev
```

## 2. Put the files in place, with the Worker's URL

```bash
cd ~/Documents/codes/telegraph-code-patch-verify
BASE_URL=https://cpv-adapter.<subdomain>.workers.dev RUN=CODE_PATCH_VERIFY_r3 bash adapter-host/prepare.sh
cd adapter-host && npx wrangler deploy && cd ..
curl -sL https://cpv-adapter.<subdomain>.workers.dev/CODE_PATCH_VERIFY.safetensors | shasum -a 256
```

`prepare.sh` copies the package (checked against the adapterbuild manifest), builds the executor, writes
`space/config.json` and prints the keccak256 to register as `wasmHash`. The downloaded sha256 must equal the
package sha256 it printed.

## 3. Create the Space

On huggingface.co: New Space, SDK **Gradio**, hardware **ZeroGPU** (the only free option for new Spaces on a
free account; CPU basic needs PRO), visibility **Public**. Upload the
four files in `space/` (`app.py`, `config.json`, `requirements.txt`, `README.md`), or push them with git.
The first start downloads the 600 MB foundation from GitHub and takes a few minutes; the Space page shows
"executor running: True" when it is ready. Hugging Face's proxy only lets POST through under `/gradio_api/`,
so the runnable URL ends in `/gradio_api/score` (the executor accepts any path).

## 4. Check it like a validator

```bash
python3 space/check.py https://<user>-<space>.hf.space/gradio_api/score 2   # identity only
python3 space/check.py https://<user>-<space>.hf.space/gradio_api/score     # 30 full-length texts, timed (limit 30 min)
```

`adapter_hash` must be the keccak256 from step 2 (without `0x`).

## 5. Register

`registerWasm(wasmHash, wasmUrl, "CODE_PATCH_VERIFY", feeAddress, wasmRunnableUrl)` after approving the
adapter bond in MACHINA. A retrained package is a new hash: repeat steps 2-5 (re-upload `config.json`).
