from __future__ import annotations

import json

from mynah.config import corpus_cache
from mynah.core.corpus import find_clusters, scan_transcripts


def test_pending_count_zero_when_no_cache(tmp_config_dir):
    assert corpus_cache.pending_count() == 0


def test_save_and_load_roundtrip(tmp_config_dir):
    clusters = [
        corpus_cache.CachedCluster(words=[["덱스", 12], ["데스", 3]], reviewed=False),
        corpus_cache.CachedCluster(words=[["머지", 8], ["머시", 2]], reviewed=True),
    ]
    corpus_cache.save(clusters)
    loaded = corpus_cache.load()
    assert len(loaded) == 2
    assert loaded[0].words == [["덱스", 12], ["데스", 3]]
    assert loaded[0].reviewed is False
    assert loaded[1].reviewed is True


def test_pending_count_counts_unreviewed(tmp_config_dir):
    clusters = [
        corpus_cache.CachedCluster(words=[["덱스", 12], ["데스", 3]], reviewed=False),
        corpus_cache.CachedCluster(words=[["머지", 8], ["머시", 2]], reviewed=True),
    ]
    corpus_cache.save(clusters)
    assert corpus_cache.pending_count() == 1


def test_load_returns_empty_on_corrupt_file(tmp_config_dir):
    corpus_cache.cache_path().write_text("not json", encoding="utf-8")
    assert corpus_cache.load() == []


def test_scan_transcripts_counts_known_words(tmp_path):
    # 컴퓨터/데이터/소프트웨어 are NNG tokens kiwipiepy reliably recognizes.
    (tmp_path / "a.txt").write_text(
        "컴퓨터 컴퓨터 데이터 데이터 데이터", encoding="utf-8"
    )
    (tmp_path / "b.txt").write_text(
        "데이터 소프트웨어 소프트웨어 소프트웨어", encoding="utf-8"
    )
    freq = scan_transcripts([tmp_path])
    assert freq.get("데이터", 0) >= 3
    assert freq.get("컴퓨터", 0) >= 1


def test_scan_transcripts_skips_missing_dir(tmp_path):
    freq = scan_transcripts([tmp_path / "nonexistent"])
    assert freq == {}


def test_scan_transcripts_deduplicates_paths(tmp_path):
    (tmp_path / "a.txt").write_text(
        "컴퓨터 컴퓨터 컴퓨터 컴퓨터", encoding="utf-8"
    )
    freq = scan_transcripts([tmp_path, tmp_path])
    assert freq.get("컴퓨터", 0) == 4


def test_find_clusters_groups_similar_words():
    freq = {"덱스": 12, "데스": 5, "뎁스": 3}
    clusters = find_clusters(freq)
    assert len(clusters) >= 1
    matched = [c for c in clusters if any(w == "덱스" for w, _ in c.words)]
    assert matched, "덱스 not found in any cluster"
    cluster_words = {w for w, _ in matched[0].words}
    assert {"덱스", "데스", "뎁스"}.issubset(cluster_words), (
        f"expected all three words in the same cluster, got: {cluster_words}"
    )


def test_find_clusters_excludes_below_min_freq():
    freq = {"덱스": 2, "데스": 1}
    clusters = find_clusters(freq)
    assert clusters == []


def test_find_clusters_sorted_by_total_frequency():
    freq = {"덱스": 15, "데스": 5, "머지": 4, "머시": 3}
    clusters = find_clusters(freq)
    totals = [c.total_frequency for c in clusters]
    assert totals == sorted(totals, reverse=True)


def test_cluster_representative_is_highest_freq_word():
    freq = {"덱스": 12, "데스": 5, "뎁스": 3}
    clusters = find_clusters(freq)
    if clusters:
        assert clusters[0].representative == "덱스"


def test_find_clusters_does_not_merge_unrelated_words():
    # 스택 and 뎁스 differ in both meaning and phonetics; they must not cluster together.
    freq = {"스택": 10, "뎁스": 8, "스텍": 5}
    clusters = find_clusters(freq)
    for cluster in clusters:
        words_in = {w for w, _ in cluster.words}
        assert not ({"스택", "뎁스"}.issubset(words_in)), (
            f"스택 and 뎁스 ended up in the same cluster: {words_in}"
        )


def test_find_clusters_threshold_symmetry():
    # Pairs with mismatched thresholds (3-syllable=1, 4-syllable=2) must use max(t_i, t_j)
    # so the result is independent of input order; distance ≤2 should cluster them.
    freq_a = {"가나다": 5, "가나다라": 5}
    freq_b = {"가나다라": 5, "가나다": 5}
    clusters_a = find_clusters(freq_a)
    clusters_b = find_clusters(freq_b)
    words_a = sorted({w for c in clusters_a for w, _ in c.words})
    words_b = sorted({w for c in clusters_b for w, _ in c.words})
    assert words_a == words_b


def test_load_skips_corrupt_entry_preserves_rest(tmp_config_dir):
    raw = json.dumps([
        {"words": [["덱스", 12], ["데스", 3]], "reviewed": False},
        {"BROKEN": True},
        {"words": [["머지", 8]], "reviewed": True},
    ])
    corpus_cache.cache_path().write_text(raw, encoding="utf-8")
    loaded = corpus_cache.load()
    assert len(loaded) == 2
    assert loaded[0].words == [["덱스", 12], ["데스", 3]]
    assert loaded[1].words == [["머지", 8]]
