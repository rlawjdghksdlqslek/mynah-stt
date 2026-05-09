"""argparse-based CLI: `mynah <audio_file> [flags]`."""

from __future__ import annotations

import argparse
import shutil
import sys
from collections.abc import Sequence
from pathlib import Path

from mynah import __version__
from mynah.config import settings as settings_mod
from mynah.core import audio as audio_mod
from mynah.core.pipeline import PipelineOptions
from mynah.core.pipeline import run as run_pipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mynah",
        description="Local-first transcription tool for Korean meetings.",
    )
    parser.add_argument("audio", nargs="?", help="Audio file to transcribe (m4a/mp3/wav/...)")
    parser.add_argument("--diarize", action="store_true", help="Speaker diarization")
    parser.add_argument(
        "--timestamps", action="store_true", help="Word-level timestamps in output"
    )
    parser.add_argument(
        "--denoise",
        action="store_true",
        help="Pre-clean audio with Demucs (requires `mynah-stt[denoise]`)",
    )
    parser.add_argument(
        "--model",
        default=None,
        choices=["large-v3", "large-v3-turbo", "turbo"],
        help="Whisper model (default: from config or large-v3)",
    )
    parser.add_argument(
        "--lang",
        default=None,
        help="Language code (default: ko). Use 'auto' to detect.",
    )
    parser.add_argument("--setup", action="store_true", help="Run interactive setup wizard")
    parser.add_argument(
        "--edit-glossary", action="store_true", help="Open the TUI glossary editor"
    )
    parser.add_argument(
        "--edit-replacements",
        action="store_true",
        help="Open the TUI replacements editor",
    )
    parser.add_argument(
        "--doctor",
        action="store_true",
        help="Check system dependencies and configuration",
    )
    parser.add_argument("--version", action="version", version=f"mynah {__version__}")
    return parser


def _preflight(opts: PipelineOptions) -> list[str]:
    """Return a list of human-readable problems; empty list means OK."""
    problems: list[str] = []
    if shutil.which("ffmpeg") is None:
        problems.append("ffmpeg not found. Install: brew install ffmpeg")
    if opts.diarize and not opts.hf_token:
        problems.append(
            "HuggingFace token not configured. Run: mynah --setup\n"
            "  (Diarization needs the pyannote model which requires accepting"
            " its terms at https://hf.co/pyannote/speaker-diarization-3.1)"
        )
    return problems


def _print_progress(stage: str, message: str, progress: float | None) -> None:
    bar = ""
    if progress is not None:
        filled = int(progress * 20)
        bar = " [" + "#" * filled + "-" * (20 - filled) + f"] {int(progress * 100):3d}%"
    print(f"  [{stage}] {message}{bar}", file=sys.stderr)


def _run_doctor() -> int:
    """Print a dependency / configuration health check and return exit code."""
    import sys as _sys

    has_errors = False

    def ok(label: str, detail: str = "") -> None:
        suffix = f"  ({detail})" if detail else ""
        print(f"  ✅  {label}{suffix}")

    def warn(label: str, detail: str = "") -> None:
        suffix = f"  ({detail})" if detail else ""
        print(f"  ⚠️   {label}{suffix}")

    def fail(label: str, detail: str = "") -> None:
        nonlocal has_errors
        has_errors = True
        suffix = f"  ({detail})" if detail else ""
        print(f"  ❌  {label}{suffix}")

    print("mynah --doctor")
    print("-" * 44)

    v = _sys.version_info
    py_str = f"Python {v.major}.{v.minor}.{v.micro}"
    if (3, 10) <= (v.major, v.minor) < (3, 13):
        ok(py_str, "compatible")
    else:
        fail(py_str, "3.10–3.12 required (3.13+ not yet stable for ML stack)")

    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path:
        ok("ffmpeg", ffmpeg_path)
    else:
        fail("ffmpeg", "brew install ffmpeg")

    try:
        import sounddevice as _sd
        ok("sounddevice", _sd.__version__)
    except ImportError:
        fail("sounddevice", "pipx runpip mynah-stt install sounddevice")

    try:
        import torch as _torch
        ok("torch", _torch.__version__)
    except ImportError:
        fail("torch", "installed via whisperx — reinstall")

    try:
        import torchaudio as _ta
        if hasattr(_ta, "list_audio_backends"):
            ok("torchaudio", _ta.__version__)
        else:
            fail(
                "torchaudio",
                f"{_ta.__version__} — list_audio_backends missing; "
                "run: pipx runpip mynah-stt install --upgrade torchaudio",
            )
    except ImportError:
        fail("torchaudio", "installed via whisperx — reinstall")

    try:
        import ctranslate2 as _ct2
        parts = tuple(int(x) for x in _ct2.__version__.split(".")[:2])
        if parts >= (4, 0):
            ok("ctranslate2", _ct2.__version__)
        else:
            fail(
                "ctranslate2",
                f"{_ct2.__version__} (<4.0 has fds_to_keep bug on macOS); "
                "run: pipx runpip mynah-stt install --upgrade ctranslate2",
            )
    except ImportError:
        fail("ctranslate2", "installed via whisperx — reinstall")

    try:
        import whisperx as _wx  # type: ignore
        ver = getattr(_wx, "__version__", "installed")
        ok("whisperx", ver)
    except ImportError:
        fail("whisperx", "pipx runpip mynah-stt install whisperx")

    print()

    from mynah.core.model_cache import is_whisper_cached
    settings = settings_mod.load()
    if is_whisper_cached(settings.model):
        ok(f"Whisper {settings.model}", "cached")
    else:
        warn(
            f"Whisper {settings.model}",
            "not cached — ~3 GB download on first transcription",
        )

    if settings.hf_token:
        ok("HuggingFace token", "configured")
    else:
        warn("HuggingFace token", "not set (required for --diarize; run: mynah --setup)")

    print()
    if has_errors:
        print("  Fix the ❌ items above, then re-run: mynah --doctor")
        return 1
    print("  All required dependencies OK.")
    return 0


def _run_setup() -> int:
    """Interactive setup: ask for HuggingFace token and persist it."""
    print("mynah setup")
    print("-----------")
    print(
        "Diarization (speaker separation) requires a free HuggingFace token.\n"
        "1. Create account: https://huggingface.co/join\n"
        "2. Accept terms:  https://hf.co/pyannote/speaker-diarization-3.1\n"
        "3. Create token:  https://huggingface.co/settings/tokens (read-only is fine)\n"
    )
    settings = settings_mod.load()
    current = settings.hf_token
    prompt = "Paste your HuggingFace token"
    if current:
        prompt += " (press Enter to keep existing)"
    prompt += ": "
    try:
        token = input(prompt).strip()
    except (KeyboardInterrupt, EOFError):
        print("\nSetup cancelled.")
        return 1
    if token:
        settings.hf_token = token
    elif not current:
        print("No token provided; diarization will be unavailable until you re-run --setup.")
    saved_to = settings_mod.save(settings)
    print(f"Saved to {saved_to}")
    return 0


def run_cli(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.doctor:
        return _run_doctor()

    if args.setup:
        return _run_setup()

    if args.edit_glossary or args.edit_replacements:
        from mynah.tui.app import run_editor_only
        target = "glossary" if args.edit_glossary else "replacements"
        return run_editor_only(target)

    if not args.audio:
        parser.print_help(sys.stderr)
        return 2

    settings = settings_mod.load()
    model = args.model or settings.model
    if model == "turbo":
        model = "large-v3-turbo"
    opts = PipelineOptions(
        diarize=args.diarize or settings.diarize,
        timestamps=args.timestamps or settings.timestamps,
        denoise=args.denoise or settings.denoise,
        model=model,
        language=args.lang or settings.language,
        hf_token=settings.hf_token,
    )

    problems = _preflight(opts)
    if problems:
        for p in problems:
            print(f"error: {p}", file=sys.stderr)
        return 2

    audio_path = Path(args.audio).expanduser()
    if not audio_path.exists():
        print(f"error: file not found: {audio_path}", file=sys.stderr)
        return 2

    try:
        result = run_pipeline(audio_path, opts, on_progress=_print_progress)
    except (audio_mod.AudioError, KeyboardInterrupt) as exc:
        print(f"\nerror: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 — surface any other failure
        print(f"\nerror: {exc}", file=sys.stderr)
        return 1

    print(f"\nWrote {result.output_path}")
    return 0
