"""WhisperX transcription wrapper.

WhisperX is loaded lazily so the rest of the package can be imported (and
tests can run) without the heavy ML stack installed.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path
from typing import Any

# Prevent ctranslate2 / tokenizers from forking subprocesses on macOS.
# Without this, Python's multiprocessing raises "bad value(s) in fds_to_keep"
# when Textual's async event loop has open file descriptors at model load time.
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

ProgressCb = Callable[[str, float | None], None] | None


class TranscribeError(Exception):
    pass


def _import_whisperx():
    try:
        import whisperx  # type: ignore
    except ImportError as exc:
        raise TranscribeError(
            "whisperx is not installed. Run: pipx install -e . (or pip install whisperx)"
        ) from exc
    return whisperx


def pick_compute_type() -> str:
    """faster-whisper / CTranslate2 compute type for Apple Silicon CPU."""
    return "int8"


MLX_REPO_MAP = {
    "large-v3": "mlx-community/whisper-large-v3-mlx",
}


def mlx_repo_for(model_name: str) -> str:
    return MLX_REPO_MAP.get(model_name, f"mlx-community/whisper-{model_name}-mlx")


def _has_mlx() -> bool:
    try:
        import mlx_whisper  # type: ignore # noqa: F401
    except Exception:
        # Not just ImportError: a half-installed mlx raises OSError/RuntimeError
        # from the Metal dylib load. Any failure here means "no usable MLX",
        # and the whole point of auto-detection is to fall back, not crash.
        return False
    return True


def pick_backend(preference: str = "auto") -> str:
    """Resolve which engine to use.

    MLX runs on the Mac's GPU; CTranslate2 (WhisperX) has no Metal backend and
    is CPU-only — measured at 0.86x realtime, i.e. slower than the recording
    itself. MLX is the default wherever it is available.
    """
    if preference == "auto":
        return "mlx" if _has_mlx() else "whisperx"
    if preference == "mlx":
        if not _has_mlx():
            raise TranscribeError(
                "backend='mlx' requested but mlx-whisper is not installed. "
                "Install: pip install mlx-whisper (Apple Silicon only)"
            )
        return "mlx"
    if preference == "whisperx":
        return "whisperx"
    raise TranscribeError(f"unknown backend {preference!r}; expected auto, mlx, or whisperx")


def _transcribe_pcm_mlx(
    pcm: bytes, *, model_name: str, language: str, initial_prompt: str
) -> dict[str, Any]:
    import mlx_whisper  # type: ignore
    import numpy as np  # type: ignore

    audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
    kwargs: dict[str, Any] = {
        "path_or_hf_repo": mlx_repo_for(model_name),
        "language": language if language != "auto" else None,
    }
    if initial_prompt:
        kwargs["initial_prompt"] = initial_prompt
    # mlx-whisper 0.4.3 raises NotImplementedError for beam_size — greedy only.
    # Gain normalization plus chunking covers what beam search was suppressing;
    # live.py retries any chunk that still loops on the WhisperX path.
    result = mlx_whisper.transcribe(audio, **kwargs)
    return {
        "segments": result.get("segments", []),
        "language": result.get("language", language),
        "text": result.get("text", ""),
    }


@lru_cache(maxsize=2)
def _load_faster_whisper(model_name: str, compute_type: str):
    """One model instance per (model, compute_type).

    Constructing WhisperModel reads ~1.5 GB from disk. The loop-retry path
    calls this once per bad chunk, so building it fresh each time was the
    dominant cost of a noisy meeting.
    """
    from faster_whisper import WhisperModel  # type: ignore

    return WhisperModel(model_name, device="cpu", compute_type=compute_type)


def _transcribe_pcm_whisperx(
    pcm: bytes,
    *,
    model_name: str,
    language: str,
    initial_prompt: str,
    beam_size: int = 5,
) -> dict[str, Any]:
    """CPU path. Also the retry path for chunks that loop under MLX greedy —
    beam search suppresses the repetition that greedy falls into."""
    import numpy as np  # type: ignore

    audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
    model = _load_faster_whisper(model_name, pick_compute_type())
    segs, info = model.transcribe(
        audio,
        language=language if language != "auto" else None,
        beam_size=beam_size,
        initial_prompt=initial_prompt or None,
    )
    out = [{"start": s.start, "end": s.end, "text": s.text} for s in segs]
    return {
        "segments": out,
        "language": getattr(info, "language", language),
        "text": " ".join(s["text"].strip() for s in out),
    }


def transcribe_pcm(
    pcm: bytes,
    *,
    model_name: str = "large-v3",
    language: str = "ko",
    initial_prompt: str = "",
    backend: str = "auto",
    beam_size: int | None = None,
) -> dict[str, Any]:
    """Transcribe a raw 16 kHz mono int16 PCM buffer (one chunk)."""
    chosen = pick_backend(backend)
    if chosen == "mlx":
        return _transcribe_pcm_mlx(
            pcm,
            model_name=model_name,
            language=language,
            initial_prompt=initial_prompt,
        )
    return _transcribe_pcm_whisperx(
        pcm,
        model_name=model_name,
        language=language,
        initial_prompt=initial_prompt,
        beam_size=beam_size or 5,
    )


def transcribe_wav(
    wav_path: Path,
    *,
    model_name: str = "large-v3",
    language: str = "ko",
    initial_prompt: str = "",
    backend: str = "auto",
) -> dict[str, Any]:
    """Transcribe a whole 16 kHz mono WAV on the fastest available engine.

    `transcribe()` below is pinned to WhisperX on the CPU at 0.86x realtime,
    because diarization needs its word-level alignment. Everything else can
    take the MLX GPU path the live recorder already uses, which measures
    7.8-10.9x realtime on the same model.
    """
    import wave

    with wave.open(str(wav_path), "rb") as w:
        pcm = w.readframes(w.getnframes())
    return transcribe_pcm(
        pcm,
        model_name=model_name,
        language=language,
        initial_prompt=initial_prompt,
        backend=backend,
    )


def transcribe(
    wav_path: Path,
    *,
    model_name: str = "large-v3",
    language: str = "ko",
    beam_size: int = 5,
    initial_prompt: str = "",
    hotwords: str = "",
    align_words: bool = False,
    on_progress: ProgressCb = None,
) -> dict[str, Any]:
    """Run WhisperX on the given 16kHz mono WAV file.

    Returns a dict with at least {'segments': [...], 'language': 'ko'}.
    If align_words=True, segments will contain word-level timestamps
    (used for both --timestamps formatting and as input for diarization).
    """
    whisperx = _import_whisperx()

    if on_progress:
        on_progress("loading model", None)

    asr_options: dict[str, Any] = {"beam_size": beam_size}
    if initial_prompt:
        asr_options["initial_prompt"] = initial_prompt
    if hotwords:
        asr_options["hotwords"] = hotwords

    model = whisperx.load_model(
        model_name,
        device="cpu",
        compute_type=pick_compute_type(),
        language=language if language != "auto" else None,
        asr_options=asr_options,
        vad_method="pyannote",
        vad_options={"vad_onset": 0.5, "vad_offset": 0.363},
    )

    if on_progress:
        on_progress("loading audio", None)

    audio = whisperx.load_audio(str(wav_path))

    if on_progress:
        on_progress("transcribing", 0.0)

    result = model.transcribe(
        audio,
        batch_size=8,
        language=language if language != "auto" else None,
    )

    if on_progress:
        on_progress("transcribing", 1.0)

    if align_words:
        if on_progress:
            on_progress("aligning words", 0.0)
        try:
            align_model, metadata = whisperx.load_align_model(
                language_code=result.get("language", language),
                device="cpu",
            )
            result = whisperx.align(
                result["segments"],
                align_model,
                metadata,
                audio,
                device="cpu",
                return_char_alignments=False,
            )
        except (ValueError, KeyError, RuntimeError) as exc:
            # Some languages don't have an alignment model bundled with WhisperX.
            # Continue without word-level timestamps.
            if on_progress:
                on_progress(f"alignment skipped ({exc})", 1.0)
        else:
            if on_progress:
                on_progress("aligning words", 1.0)

    # Stash the audio for downstream stages (diarization needs it)
    result.setdefault("language", language)
    result["_audio"] = audio
    return result
