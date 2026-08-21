"""Backend selection — no model download required."""

from __future__ import annotations

import builtins

import pytest

from mynah.core import transcribe as t


class TestPickBackend:
    def test_prefers_mlx_when_importable(self, monkeypatch):
        monkeypatch.setattr(t, "_has_mlx", lambda: True)
        assert t.pick_backend("auto") == "mlx"

    def test_falls_back_when_mlx_missing(self, monkeypatch):
        monkeypatch.setattr(t, "_has_mlx", lambda: False)
        assert t.pick_backend("auto") == "whisperx"

    def test_explicit_whisperx_is_honored(self, monkeypatch):
        monkeypatch.setattr(t, "_has_mlx", lambda: True)
        assert t.pick_backend("whisperx") == "whisperx"

    def test_explicit_mlx_without_mlx_raises(self, monkeypatch):
        monkeypatch.setattr(t, "_has_mlx", lambda: False)
        with pytest.raises(t.TranscribeError, match="mlx"):
            t.pick_backend("mlx")

    def test_unknown_preference_raises(self):
        with pytest.raises(t.TranscribeError):
            t.pick_backend("nonsense")


class TestHasMlx:
    def test_reports_false_when_import_fails(self, monkeypatch):
        real_import = builtins.__import__

        def blocked(name, *args, **kwargs):
            if name.startswith("mlx"):
                raise ImportError("blocked")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", blocked)
        assert t._has_mlx() is False


class TestModelRepoMapping:
    def test_large_v3_maps_to_mlx_community_repo(self):
        assert t.MLX_REPO_MAP["large-v3"] == "mlx-community/whisper-large-v3-mlx"

    def test_unknown_model_falls_back_to_naming_convention(self):
        assert t.mlx_repo_for("small") == "mlx-community/whisper-small-mlx"


class TestBackendShapeParity:
    """Task 7 calls one backend, then the other as a retry, and reads the same
    keys from whichever answered. A shape mismatch would fail silently."""

    def _fake_modules(self, monkeypatch):
        import sys
        import types

        mlx = types.ModuleType("mlx_whisper")
        mlx.transcribe = lambda audio, **kw: {
            "segments": [{"start": 0.0, "end": 1.0, "text": "가"}],
            "language": "ko",
            "text": "가",
        }
        monkeypatch.setitem(sys.modules, "mlx_whisper", mlx)

        class FakeSeg:
            start, end, text = 0.0, 1.0, "가"

        class FakeInfo:
            language = "ko"

        class FakeModel:
            def __init__(self, *a, **kw):
                pass

            def transcribe(self, audio, **kw):
                return [FakeSeg()], FakeInfo()

        fw = types.ModuleType("faster_whisper")
        fw.WhisperModel = FakeModel
        monkeypatch.setitem(sys.modules, "faster_whisper", fw)

    def test_both_backends_return_the_same_keys(self, monkeypatch):
        self._fake_modules(monkeypatch)
        pcm = b"\x00\x01" * 100

        a = t._transcribe_pcm_mlx(pcm, model_name="large-v3", language="ko", initial_prompt="")
        b = t._transcribe_pcm_whisperx(
            pcm, model_name="large-v3", language="ko", initial_prompt="", beam_size=5
        )

        assert set(a) == set(b) == {"segments", "language", "text"}

    def test_transcribe_pcm_routes_to_the_chosen_backend(self, monkeypatch):
        self._fake_modules(monkeypatch)
        monkeypatch.setattr(t, "_has_mlx", lambda: True)

        out = t.transcribe_pcm(b"\x00\x01" * 100, backend="auto")
        assert out["text"] == "가"
        assert out["language"] == "ko"
