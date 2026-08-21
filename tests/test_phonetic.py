from __future__ import annotations

from mynah.core.phonetic import decompose, jamo_distance, similarity_threshold


def test_decompose_returns_jamo_string():
    result = decompose("덱스")
    assert "ㄷ" in result
    assert "ㄱ" in result
    assert "ㅅ" in result


def test_decompose_non_hangul_passthrough():
    assert decompose("deps") == "deps"


def test_decompose_mixed():
    result = decompose("AI뎁스")
    assert result.startswith("AI")
    assert "ㄷ" in result


def test_jamo_distance_identical():
    assert jamo_distance("뎁스", "뎁스") == 0


def test_jamo_distance_close_pair():
    assert jamo_distance("덱스", "뎁스") <= 3


def test_jamo_distance_far_pair():
    assert jamo_distance("스택", "뎁스") > 4


def test_jamo_distance_asymmetric_length():
    assert jamo_distance("데스", "뎁스") <= 4


def test_similarity_threshold_proportional():
    short = similarity_threshold("가나")
    long_ = similarity_threshold("가나다라마")
    assert long_ > short


def test_similarity_threshold_minimum_one():
    assert similarity_threshold("가") >= 1
