"""Lightweight keyword retrieval over the Avis knowledge base.

The knowledge base is ~30 short help-center articles, so a vector DB is overkill.
This does TF-style keyword scoring in plain Python: tokens are matched against
each article's title (weighted 2x) and body (weighted 1x), after stop-word
removal. Good enough to surface the right policy article for a cancellation.

Articles are loaded once at import time.
"""
from __future__ import annotations

import json
import math
import os
import re
from collections import Counter

_KB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "knowledge-base", "articles.json",
)

# Small stop-word list — enough to drop noise from natural-language queries.
_STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "can", "do", "does", "for",
    "from", "how", "i", "if", "in", "is", "it", "its", "me", "my", "no", "not",
    "of", "on", "or", "the", "to", "want", "was", "what", "when", "where",
    "which", "will", "with", "would", "you", "your",
}

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall(text.lower()) if t not in _STOP_WORDS]


def _load_articles() -> list[dict]:
    with open(_KB_PATH, encoding="utf-8") as f:
        articles = json.load(f)
    for art in articles:
        title_tokens = Counter(_tokenize(art["title"]))
        body_tokens = Counter(_tokenize(art["body"]))
        # Title terms count double — a title hit is a stronger topical signal.
        combined = Counter()
        for tok, n in title_tokens.items():
            combined[tok] += 2 * n
        for tok, n in body_tokens.items():
            combined[tok] += n
        art["_tokens"] = combined
    return articles


_ARTICLES = _load_articles()

# Inverse-document-frequency so common words ("rental", "fee") count for less
# than distinctive ones ("cancel", "no-show", "refund").
_N_DOCS = len(_ARTICLES)
_DF: Counter = Counter()
for _art in _ARTICLES:
    for _tok in _art["_tokens"]:
        _DF[_tok] += 1
_IDF = {tok: math.log((_N_DOCS + 1) / (df + 1)) + 1 for tok, df in _DF.items()}


def _score(query_tokens: list[str], article: dict) -> float:
    weights = article["_tokens"]
    return sum(weights.get(tok, 0) * _IDF.get(tok, 1.0) for tok in query_tokens)


def search_knowledge_base(query: str, top_k: int = 3) -> str:
    """Return the top-k most relevant KB articles as formatted text.

    Each result is rendered as "Title\n<body>" so the agent can quote policy
    accurately. Returns a clear no-match message rather than an empty string.
    """
    query_tokens = _tokenize(query)
    if not query_tokens:
        return "No search terms provided."

    scored = [(_score(query_tokens, art), art) for art in _ARTICLES]
    scored = [(s, art) for s, art in scored if s > 0]
    scored.sort(key=lambda pair: pair[0], reverse=True)

    if not scored:
        return f"No knowledge-base articles matched '{query}'."

    blocks = []
    for _, art in scored[:top_k]:
        blocks.append(f"## {art['title']} ({art['category']})\n{art['body']}")
    return "\n\n".join(blocks)


if __name__ == "__main__":
    for q in ["cancel my reservation refund", "no show", "what does it cost to cancel late"]:
        print(f"\n=== QUERY: {q} ===")
        print(search_knowledge_base(q, top_k=2))
