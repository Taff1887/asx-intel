"""
Extractive summarisation via TextRank — no LLM / API key required.

Picks the most *central* sentences from a document using a PageRank-style
algorithm over a sentence-similarity graph (Mihalcea & Tarau, 2004).

Pure-Python + numpy: no nltk, no sklearn, no model downloads — so it deploys
cleanly on Render's free tier.

This is the no-API fallback. When an LLM key is configured the abstractive LLM
summary is used instead — that one can *explain and infer* (e.g. why a stock
moved); this one only *selects* the most representative existing sentences.
"""

import logging
import math
import re

logger = logging.getLogger(__name__)

# Minimal inline stopword list — avoids an nltk download on the server
_STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "if", "then", "else", "when", "at",
    "by", "for", "with", "about", "against", "between", "into", "through",
    "during", "before", "after", "above", "below", "to", "from", "up", "down",
    "in", "out", "on", "off", "over", "under", "again", "further", "is", "are",
    "was", "were", "be", "been", "being", "have", "has", "had", "having", "do",
    "does", "did", "doing", "of", "this", "that", "these", "those", "it", "its",
    "as", "will", "would", "should", "could", "may", "might", "can", "shall",
    "we", "our", "ours", "you", "your", "they", "their", "them", "he", "she",
    "his", "her", "i", "me", "my", "not", "no", "so", "than", "too", "very",
    "just", "also", "which", "who", "whom", "what", "where", "there", "here",
}


def _tokenize(sentence: str) -> list[str]:
    """Lowercase word tokens, stopwords and short tokens removed."""
    words = re.findall(r"[a-zA-Z][a-zA-Z0-9'-]+", sentence.lower())
    return [w for w in words if w not in _STOPWORDS and len(w) > 2]


def _similarity(words_i: list[str], words_j: list[str]) -> float:
    """TextRank sentence similarity: shared words normalised by log lengths."""
    if not words_i or not words_j:
        return 0.0
    set_i, set_j = set(words_i), set(words_j)
    common = len(set_i & set_j)
    if common == 0:
        return 0.0
    norm = math.log(len(set_i) + 1) + math.log(len(set_j) + 1)
    return common / norm if norm else 0.0


def textrank(sentences: list[str], top_n: int = 5, max_sentences: int = 120) -> list[str]:
    """
    Return the top_n most central sentences, in original document order.

    Falls back to the first top_n sentences if numpy is unavailable or the
    graph is degenerate (no word overlap anywhere).
    """
    n = len(sentences)
    if n == 0:
        return []
    if n <= top_n:
        return sentences

    # Cap for performance — similarity matrix is O(n^2)
    if n > max_sentences:
        sentences = sentences[:max_sentences]
        n = max_sentences

    try:
        import numpy as np
    except ImportError:
        logger.debug("numpy unavailable — extractive summariser using first %d sentences", top_n)
        return sentences[:top_n]

    tokens = [_tokenize(s) for s in sentences]

    # Build symmetric similarity matrix
    sim = np.zeros((n, n), dtype=float)
    for i in range(n):
        for j in range(i + 1, n):
            s = _similarity(tokens[i], tokens[j])
            if s:
                sim[i, j] = s
                sim[j, i] = s

    # Column-normalise into a transition matrix (each column sums to 1)
    col_sums = sim.sum(axis=0)
    col_sums[col_sums == 0] = 1.0
    transition = sim / col_sums

    # PageRank power iteration
    d = 0.85
    scores = np.ones(n) / n
    for _ in range(100):
        prev = scores.copy()
        scores = (1.0 - d) / n + d * transition.dot(scores)
        if np.abs(scores - prev).sum() < 1e-6:
            break

    # Highest-scoring indices, returned in original document order for readability
    ranked = sorted(range(n), key=lambda idx: scores[idx], reverse=True)[:top_n]
    ranked.sort()
    return [sentences[idx] for idx in ranked]
