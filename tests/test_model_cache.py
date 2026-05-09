"""Tests for the WhisperX model cache detector."""

from __future__ import annotations

from mynah.core import model_cache


class TestIsWhisperCached:
    def test_no_cache_dir_returns_false(self, tmp_path, monkeypatch):
        monkeypatch.setattr(model_cache, "_HF_CACHE_DIR", tmp_path / "missing")
        assert model_cache.is_whisper_cached() is False

    def test_empty_cache_dir_returns_false(self, tmp_path, monkeypatch):
        monkeypatch.setattr(model_cache, "_HF_CACHE_DIR", tmp_path)
        assert model_cache.is_whisper_cached() is False

    def test_with_cached_model_returns_true(self, tmp_path, monkeypatch):
        monkeypatch.setattr(model_cache, "_HF_CACHE_DIR", tmp_path)
        (tmp_path / "models--Systran--faster-whisper-large-v3").mkdir()
        assert model_cache.is_whisper_cached() is True

    def test_with_turbo_model_returns_true(self, tmp_path, monkeypatch):
        monkeypatch.setattr(model_cache, "_HF_CACHE_DIR", tmp_path)
        (tmp_path / "models--Systran--faster-whisper-large-v3-turbo").mkdir()
        assert model_cache.is_whisper_cached(model="turbo") is True
