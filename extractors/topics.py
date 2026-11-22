"""Modellazione degli argomenti (LDA) sul corpus raccolto: non supervisionata, nessun addestramento su etichette."""

from __future__ import annotations

from typing import Any

from extractors.text import STOP


def topics(texts: list[str], n_topics: int = 6, n_words: int = 8) -> list[dict[str, Any]]:
    from sklearn.decomposition import LatentDirichletAllocation
    from sklearn.feature_extraction.text import CountVectorizer

    from extractors.normalize import normalize_text

    docs = [normalize_text(t) for t in texts if t and len(t) > 20]
    if len(docs) < max(5, n_topics):
        return []
    stop = sorted(STOP["it"] | STOP["en"] | STOP["es"] | {"https", "http", "www", "com"})
    vectorizer = CountVectorizer(max_df=0.9, min_df=2, stop_words=stop, token_pattern=r"(?u)\b[^\W\d_]{3,}\b")
    try:
        counts = vectorizer.fit_transform(docs)
    except ValueError:
        return []
    lda = LatentDirichletAllocation(n_components=n_topics, random_state=0, learning_method="batch")
    weights = lda.fit_transform(counts)
    vocab = vectorizer.get_feature_names_out()
    out = []
    for k, component in enumerate(lda.components_):
        words = [vocab[i] for i in component.argsort()[::-1][:n_words]]
        docs_k = sorted(range(len(docs)), key=lambda i: -weights[i][k])[:3]
        out.append(
            {
                "argomento": k + 1,
                "parole": words,
                "peso": round(float(weights[:, k].sum() / len(docs)), 3),
                "esempi": docs_k,
            }
        )
    return sorted(out, key=lambda t: -t["peso"])
