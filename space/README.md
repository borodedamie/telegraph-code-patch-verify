---
title: CODE_PATCH_VERIFY evaluator
emoji: ✅
colorFrom: green
colorTo: gray
sdk: gradio
app_file: app.py
pinned: false
---

Executor for the Telegraph CODE_PATCH_VERIFY evaluator adapter: the kit's reference `cmd/adapterexec` on the
shared Foundation Model. Validators POST batch requests to this Space's URL (the registration's
`wasmRunnableUrl`). Every downloaded file is checked by sha256 before use; see `app.py`.

Source: https://github.com/borodedamie/telegraph-code-patch-verify
