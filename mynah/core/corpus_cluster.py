from __future__ import annotations

from mynah.core.corpus_types import Cluster
from mynah.core.phonetic import jamo_distance, similarity_threshold

MIN_FREQ = 3


def find_clusters(freq_map: dict[str, int]) -> list[Cluster]:
    """Union-find groups phonetic neighbors; pair threshold uses max(t_i, t_j) for symmetry."""
    candidates = [(w, f) for w, f in freq_map.items() if f >= MIN_FREQ]
    if not candidates:
        return []

    words = [w for w, _ in candidates]
    thresholds = [similarity_threshold(w) for w in words]
    parent = list(range(len(words)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        parent[find(i)] = find(j)

    for i in range(len(words)):
        for j in range(i + 1, len(words)):
            threshold = max(thresholds[i], thresholds[j])
            if jamo_distance(words[i], words[j]) <= threshold:
                union(i, j)

    groups: dict[int, list[tuple[str, int]]] = {}
    for i, (word, freq) in enumerate(candidates):
        root = find(i)
        groups.setdefault(root, []).append((word, freq))

    return sorted(
        [
            Cluster(words=sorted(members, key=lambda x: -x[1]))
            for members in groups.values()
            if len(members) >= 2
        ],
        key=lambda c: -c.total_frequency,
    )
