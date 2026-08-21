"""Corpus scanning and clustering — re-exports both for backward compatibility."""
from mynah.core.corpus_cluster import find_clusters
from mynah.core.corpus_scan import scan_transcripts
from mynah.core.corpus_types import Cluster

__all__ = ["scan_transcripts", "find_clusters", "Cluster"]
