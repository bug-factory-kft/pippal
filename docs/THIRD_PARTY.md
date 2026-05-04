# Third-Party Notices

PipPal itself is MIT-licensed (see [LICENSE.md](../LICENSE.md)). It depends on a
small number of third-party packages and, at run-time, expects the user
to download two upstream artefacts (the Piper engine and a voice). This
file lists what is involved and under what terms.

## Python dependencies (installed via pip)

| Package | License | Notes |
|---|---|---|
| [keyboard](https://github.com/boppreh/keyboard) | MIT | Global hotkey dispatch. |
| [pyperclip](https://github.com/asweigart/pyperclip) | BSD-3-Clause | Clipboard get/set. |
| [pystray](https://github.com/moses-palmer/pystray) | LGPL-3.0 | Tray icon. Used as an unmodified, dynamically-linked library — no LGPL obligation propagates to PipPal. |
| [Pillow](https://python-pillow.org/) | MIT-CMU (HPND) | Image generation for the tray icon. |
| [kokoro-onnx](https://github.com/thewh1teagle/kokoro-onnx) | MIT | Optional. Runs Kokoro TTS in-process. |
| [soundfile](https://github.com/bastibe/python-soundfile) | BSD-3-Clause | Optional. WAV write helper for the Kokoro path. |
| [pytest](https://pytest.org/), [ruff](https://docs.astral.sh/ruff/), [mypy](https://mypy-lang.org/) | MIT | Dev-only. |

The dependency tree is small and entirely permissive. None of these
licences require PipPal itself to adopt a copyleft licence.

## Run-time artefacts (downloaded by `setup.ps1`)

These are **not** distributed with the PipPal source repository. The
setup script fetches them from the upstream projects' release pages
when the user runs it for the first time.

### Piper

- Project: <https://github.com/rhasspy/piper>
- Licence: **MIT**
- Bundled by upstream Piper: **eSpeak NG (GPL-3.0)** as
  `espeak-ng.dll`. PipPal calls `piper.exe` as a subprocess and never
  loads `espeak-ng.dll` into its own process, so the GPL boundary
  stays inside Piper's executable. PipPal does not redistribute either
  binary — `setup.ps1` downloads the official Piper release.

### Piper voices

- Catalogue: <https://huggingface.co/rhasspy/piper-voices>
- Licences: **per voice** — see each voice's model card. Most of the
  curated voices in the Voice Manager are MIT or research-permissive
  (LibriTTS / LibriTTS-R / VCTK derivatives). PipPal does not ship
  voice files; the user downloads them on demand.

### Kokoro TTS (optional)

- Model: <https://github.com/thewh1teagle/kokoro-onnx>
- Licence: **Apache-2.0** (model and ONNX export). PipPal does not
  ship the Kokoro model; it is downloaded inside the app via the
  Kokoro install dialog.

### ONNX Runtime (bundled inside the Piper release)

- Project: <https://github.com/microsoft/onnxruntime>
- Licence: **MIT**.

## Trademarks

"Piper", "Kokoro", "ONNX", "Hugging Face", "Windows", "Microsoft" and
other product names are trademarks of their respective owners. Use of
these names in PipPal is purely descriptive.
