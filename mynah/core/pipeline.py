"""End-to-end pipeline: audio file -> txt file."""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from mynah.config import glossary as glossary_mod
from mynah.config import replacements as replacements_mod
from mynah.core import audio as audio_mod
from mynah.core import format as format_mod
from mynah.core import transcribe as transcribe_mod

ProgressCb = Callable[[str, str, float | None], None] | None
"""Progress callback: (stage, message, progress_0_to_1_or_none)"""


@dataclass
class PipelineOptions:
    diarize: bool = False
    timestamps: bool = False
    denoise: bool = False
    model: str = "large-v3"
    language: str = "ko"
    hf_token: str = ""


@dataclass
class PipelineResult:
    output_path: Path
    output_text: str
    stages_run: list[str] = field(default_factory=list)


def _unique_output_path(input_path: Path) -> Path:
    """Pick an output path that doesn't overwrite an existing file.

    `meeting.m4a` -> `meeting.txt` (or `meeting (1).txt`, `meeting (2).txt`, ...).
    """
    base = input_path.with_suffix(".txt")
    if not base.exists():
        return base
    parent = base.parent
    stem = base.stem
    n = 1
    while True:
        candidate = parent / f"{stem} ({n}).txt"
        if not candidate.exists():
            return candidate
        n += 1


def _writable_output_path(input_path: Path) -> Path:
    """Resolve an output path; fall back to ~/Documents/mynah-output/ if the
    input directory isn't writable."""
    try:
        candidate = _unique_output_path(input_path)
        candidate.parent.mkdir(parents=True, exist_ok=True)
        test = candidate.parent / f".mynah_write_test_{os.getpid()}"
        test.write_text("", encoding="utf-8")
        test.unlink()
        return candidate
    except (OSError, PermissionError):
        fallback_dir = Path.home() / "Documents" / "mynah-output"
        fallback_dir.mkdir(parents=True, exist_ok=True)
        return _unique_output_path(fallback_dir / input_path.name)


def run(
    input_path: Path,
    options: PipelineOptions,
    *,
    on_progress: ProgressCb = None,
) -> PipelineResult:
    """Run the full pipeline for a single audio file."""
    input_path = Path(input_path).expanduser().resolve()
    stages_run: list[str] = []
    tmp_files: list[Path] = []

    def _emit(stage: str, message: str, progress: float | None = None) -> None:
        if on_progress:
            on_progress(stage, message, progress)

    try:
        _emit("audio", "normalizing input to 16kHz mono", 0.0)
        wav = audio_mod.to_wav_16k_mono(input_path)
        tmp_files.append(wav)
        stages_run.append("audio")
        _emit("audio", "normalized", 1.0)

        if options.denoise:
            from mynah.core import denoise as denoise_mod  # lazy
            _emit("denoise", "running demucs (vocals stem)", 0.0)
            wav = denoise_mod.denoise(wav)
            tmp_files.append(wav)
            stages_run.append("denoise")
            _emit("denoise", "denoised", 1.0)

        terms = glossary_mod.load()
        rules = replacements_mod.load()

        def _t_progress(message: str, p: float | None) -> None:
            _emit("transcribe", message, p)

        result = transcribe_mod.transcribe(
            wav,
            model_name=options.model,
            language=options.language,
            initial_prompt=glossary_mod.as_initial_prompt(terms),
            hotwords=glossary_mod.as_hotwords(terms),
            align_words=options.timestamps or options.diarize,
            on_progress=_t_progress,
        )
        stages_run.append("transcribe")

        if options.diarize:
            from mynah.core import diarize as diarize_mod  # lazy

            def _d_progress(message: str, p: float | None) -> None:
                _emit("diarize", message, p)

            result = diarize_mod.diarize_and_assign(
                result,
                hf_token=options.hf_token,
                on_progress=_d_progress,
            )
            stages_run.append("diarize")

        _emit("format", "rendering output", 0.0)
        text = format_mod.render(
            result,
            diarize=options.diarize,
            timestamps=options.timestamps,
        )
        if rules:
            text = replacements_mod.apply(text, rules)

        out_path = _writable_output_path(input_path)
        out_path.write_text(text, encoding="utf-8")
        stages_run.append("format")
        _emit("format", f"wrote {out_path}", 1.0)

        return PipelineResult(
            output_path=out_path,
            output_text=text,
            stages_run=stages_run,
        )
    finally:
        for tmp in tmp_files:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
