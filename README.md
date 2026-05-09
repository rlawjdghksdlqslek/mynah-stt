# mynah 🐦

> **Local-first transcription for Korean meetings.**  
> Record directly or drop an audio file — get a clean `.txt` in minutes.  
> No cloud. No per-meeting cost. Runs entirely on your Mac.

[![Python 3.10–3.12](https://img.shields.io/badge/python-3.10–3.12-blue)](https://www.python.org)
[![License Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-green)](https://github.com/rlawjdghksdlqslek/mynah-stt/blob/main/LICENSE)
[![Platform macOS Apple Silicon](https://img.shields.io/badge/platform-macOS%20Apple%20Silicon-lightgrey)](https://www.apple.com/mac/)

---

## Screenshots

<div align="center">
  <img src="https://raw.githubusercontent.com/rlawjdghksdlqslek/mynah-stt/main/docs/assets/main.svg" width="80%" alt="Main screen">
</div>

<br>

<div align="center">
  <img src="https://raw.githubusercontent.com/rlawjdghksdlqslek/mynah-stt/main/docs/assets/recording.svg" width="48%" alt="Recording screen">
  <img src="https://raw.githubusercontent.com/rlawjdghksdlqslek/mynah-stt/main/docs/assets/settings.svg" width="48%" alt="Settings screen">
</div>

<br>

<div align="center">
  <img src="https://raw.githubusercontent.com/rlawjdghksdlqslek/mynah-stt/main/docs/assets/progress.svg" width="48%" alt="Progress screen">
  <img src="https://raw.githubusercontent.com/rlawjdghksdlqslek/mynah-stt/main/docs/assets/result.svg" width="48%" alt="Result screen">
</div>

---

## Features

- **Record directly in the TUI** — mic capture with pause/resume, auto-transcribes on stop
- **Or drop an existing file** — m4a, mp3, wav, flac, webm, mp4 supported
- **Korean-first** — Whisper large-v3, fixed `ko` language, VAD always on to prevent hallucinations on silence
- **English code-switching** — three-layer defense (initial_prompt + hotwords + post-process replacements) keeps project names and technical terms intact
- **Speaker diarization** — `SPEAKER_01:` labels per segment (optional, requires HF token)
- **Word-level timestamps** — `[HH:MM:SS]` prefix per segment (optional)
- **Denoising** — Demucs vocals stem strips HVAC and keyboard noise (optional)
- **Glossary & replacements** — editable inside the TUI; glossary fed into Whisper as context and hotwords
- **TUI for daily use, CLI for scripting** — both first-class, same pipeline
- **System health check** — `mynah --doctor` verifies all dependencies and shows actionable fixes
- **Offline, always** — no API calls after the first model download (~3 GB, one-time)

---

## Output formats

| Flags                    | Format                               |
| ------------------------ | ------------------------------------ |
| _(none)_                 | continuous text                      |
| `--timestamps`           | `[HH:MM:SS] sentence...`             |
| `--diarize`              | `SPEAKER_NN: sentence...`            |
| `--diarize --timestamps` | `[HH:MM:SS] SPEAKER_NN: sentence...` |

Output filename: `<input>.txt`. On collision: `<input> (1).txt`, `<input> (2).txt`, etc. — never silently overwrites.

---

## Install

### Prerequisites

| Requirement           | Version         | Install                                |
| --------------------- | --------------- | -------------------------------------- |
| macOS (Apple Silicon) | 14+             | —                                      |
| Python                | **3.10 – 3.12** | `brew install python@3.12`             |
| ffmpeg                | any             | `brew install ffmpeg`                  |
| pipx                  | any             | `brew install pipx && pipx ensurepath` |

> ⚠️ **Python 3.13+ is not yet supported** — the ML stack (torch, torchaudio, ctranslate2) does not have stable wheels for 3.13+.

### One-line install

```bash
pipx install mynah-stt

# Optional: with denoising (Demucs) support
# pipx install 'mynah-stt[denoise]'

# Optional: speaker diarization needs a free HuggingFace token
mynah --setup
```

> **Package vs. command name:** the PyPI distribution is `mynah-stt`, but the CLI you actually run is `mynah` (and Python imports are `import mynah`). The `-stt` suffix only shows up at install time — same pattern as `pip install Pillow` → `import PIL`.

> **First run:** Whisper large-v3 (~3 GB) downloads automatically on the first transcription and is cached for all subsequent runs.

---

## Quick start

```bash
mynah                               # open TUI → Record → Stop → transcript ready
mynah meeting.m4a                   # CLI: transcribe existing file
mynah meeting.m4a --diarize         # with speaker labels
mynah meeting.m4a --timestamps      # with time codes
mynah --doctor                      # check system dependencies
```

---

## TUI

Run `mynah` with no arguments to open the TUI.

**Main screen** — press `R` or `Space` to start recording, `F` to open an existing audio file, `S` for settings, `G` for glossary, `Q` to quit.

**Recording screen** — microphone captures at 16 kHz mono. The level meter shows live input amplitude. `Space` to pause/resume. `S` to stop and start transcription automatically.

**Settings** (`S` from anywhere) — toggle speaker diarization, word-level timestamps, and denoising with on/off switches; switch the Whisper model and input language; set your HuggingFace token inline without leaving the TUI.

**Result screen** — transcript is auto-copied to the clipboard the moment it appears. Open the file or reveal it in Finder directly from this screen.

---

## CLI

```bash
mynah <audio_file> [flags]
```

| Flag                  | Description                                     |
| --------------------- | ----------------------------------------------- |
| `--diarize`           | Speaker diarization (SPEAKER_NN: labels)        |
| `--timestamps`        | Word-level timestamps ([HH:MM:SS] prefixes)     |
| `--denoise`           | Denoise with Demucs (requires `mynah-stt[denoise]`) |
| `--model`             | `large-v3` (default) or `large-v3-turbo`        |
| `--lang`              | `ko` (default), `en`, `auto`                    |
| `--setup`             | Interactive HuggingFace token wizard            |
| `--doctor`            | System dependency health check                  |
| `--edit-glossary`     | Open the TUI glossary editor                    |
| `--edit-replacements` | Open the TUI replacements editor                |

---

## Glossary — the biggest quality lever

Add the project names, people, and technical terms that appear in your meetings. mynah feeds them to Whisper as context (initial_prompt + hotwords), which keeps code-switched proper nouns in their original form.

```bash
# Edit from the TUI (G key) or directly:
~/.config/mynah/glossary.txt   # one term per line
```

Example entries: `Whisper`, `Slack`, `Q3 OKR`, `홍길동`, `CTranslate2`

### Replacements (safety net)

Post-processing find/replace rules for known mistakes:

```toml
# ~/.config/mynah/replacements.toml
[[rule]]
from = "슬랙"
to = "Slack"

[[rule]]
from = "위스퍼"
to = "Whisper"
```

Set `regex = true` on any rule to use Python regex syntax.

---

## Configuration files

| Path                                | Purpose                               |
| ----------------------------------- | ------------------------------------- |
| `~/.config/mynah/config.toml`       | Last-used options (auto-saved)        |
| `~/.config/mynah/glossary.txt`      | Domain vocabulary (one term per line) |
| `~/.config/mynah/replacements.toml` | Post-processing find/replace rules    |

---

## Performance

Estimates for a 1-hour Korean meeting on MacBook Pro M5:

| Pipeline                               | Time    |
| -------------------------------------- | ------- |
| Transcription only (`large-v3`)        | ~15 min |
| + Speaker diarization                  | ~25 min |
| + Diarization + timestamps + denoising | ~35 min |

`large-v3-turbo` runs ~3–5× faster with a small accuracy trade-off.

The pipeline runs on CPU + int8 quantization (CTranslate2 / faster-whisper). On M5 this is fast enough that GPU/Neural Engine paths are not necessary.

---

## Troubleshooting

Run the built-in health check first:

```bash
mynah --doctor
```

Common issues and fixes:

| Error                         | Fix                                                                                               |
| ----------------------------- | ------------------------------------------------------------------------------------------------- |
| `ffmpeg not found`            | `brew install ffmpeg`                                                                             |
| `bad value(s) in fds_to_keep` | `pipx runpip mynah-stt install --upgrade ctranslate2`                                                |
| `list_audio_backends missing` | `pipx runpip mynah-stt install --upgrade torchaudio`                                                 |
| Python 3.13+ not supported    | `brew install python@3.12` then `pipx install mynah-stt --python /opt/homebrew/bin/python3.12 --force` |
| Microphone not captured       | macOS System Settings → Sound → Input → select the correct device                                 |

---

## Development

```bash
git clone https://github.com/rlawjdghksdlqslek/mynah-stt.git
cd mynah-stt

# Install with dev extras (editable mode — code changes take effect immediately)
pipx install -e '.[dev]'

# Unit tests — no model download required
pytest tests/

# Lint
ruff check .
```

The codebase is organized so that the **core pipeline** (`mynah/core/`) has no UI dependencies — TUI and CLI are thin wrappers over `pipeline.run()`. Unit-testable pure modules (`format`, `glossary`, `replacements`, `settings`, `model_cache`, `record`) cover the logic that doesn't need ML model downloads.

```
mynah/
├── core/         # pipeline orchestration + ML wrappers
├── config/       # settings, glossary, replacements (no ML deps)
├── cli.py        # argparse entry point
├── tui/          # Textual app + screens
│   ├── screens/  # main, record, progress, result, settings, editor
│   └── app.css   # color theme
└── app.py        # dispatches TUI vs CLI based on argv
```

---

## License

Apache-2.0. See [LICENSE](https://github.com/rlawjdghksdlqslek/mynah-stt/blob/main/LICENSE).

## Acknowledgments

- [OpenAI Whisper](https://github.com/openai/whisper) — speech recognition model
- [WhisperX](https://github.com/m-bain/whisperX) — alignment + diarization wrapper
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper) — CTranslate2-accelerated Whisper inference
- [pyannote-audio](https://github.com/pyannote/pyannote-audio) — speaker diarization
- [Textual](https://github.com/Textualize/textual) — TUI framework
- [Demucs](https://github.com/adefossez/demucs) — audio source separation
