"""Classificatore "pubblicità di gioco sì o no".

Due motori: vettori di un modello multilingue pre-addestrato (sentence-transformers)
più una regressione logistica, oppure, senza modello disponibile, n-grammi di
caratteri TF-IDF più la stessa regressione. Il motore usato è registrato nella versione.

Vincolo 3: nessun modello si addestra su dati Telegram. `train` scarta ogni esempio
con fonte Telegram e solleva un errore se gliene arriva uno senza fonte dichiarata.
"""

from __future__ import annotations

import hashlib
import io
import os
from dataclasses import dataclass
from typing import Any

FORBIDDEN_SOURCES = {"telegram"}
EMBEDDING_MODEL = os.environ.get(
    "MODELLO_VETTORI", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
)


@dataclass
class Example:
    text: str
    label: bool
    source: str


class TrainingDataError(ValueError):
    pass


def usable_for_training(examples: list[Example]) -> tuple[list[Example], int]:
    kept, dropped = [], 0
    for ex in examples:
        if not ex.source:
            raise TrainingDataError("Ogni esempio di addestramento deve dichiarare la fonte.")
        if ex.source.split(":")[0] in FORBIDDEN_SOURCES:
            dropped += 1
            continue
        kept.append(ex)
    return kept, dropped


def _embedder():
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        return None
    try:
        return SentenceTransformer(
            EMBEDDING_MODEL, local_files_only=bool(os.environ.get("MODELLI_SOLO_LOCALI"))
        )
    except Exception:  # noqa: BLE001 - modello non scaricabile: si usa il motore TF-IDF
        return None


class Classifier:
    def __init__(self, engine: str = "auto") -> None:
        self.engine = engine
        self.model: Any = None
        self.vectorizer: Any = None
        self.version = ""
        self.trained_on = 0
        self.dropped_telegram = 0

    def _features(self, texts: list[str], fit: bool = False):
        from extractors.normalize import normalize_text

        clean = [normalize_text(t) for t in texts]
        if self.engine == "vettori":
            return self.vectorizer.encode(clean, normalize_embeddings=True)
        if fit:
            return self.vectorizer.fit_transform(clean)
        return self.vectorizer.transform(clean)

    def train(self, examples: list[Example]) -> Classifier:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.linear_model import LogisticRegression

        kept, self.dropped_telegram = usable_for_training(examples)
        labels = {ex.label for ex in kept}
        if len(kept) < 10 or len(labels) < 2:
            raise TrainingDataError(
                f"Servono almeno 10 esempi non Telegram con entrambe le etichette: ne ho {len(kept)}."
            )
        if self.engine in {"auto", "vettori"}:
            embedder = _embedder()
            if embedder is not None:
                self.engine, self.vectorizer = "vettori", embedder
            elif self.engine == "vettori":
                raise TrainingDataError("Modello di vettori non disponibile.")
            else:
                self.engine = "tfidf"
        if self.engine == "tfidf":
            self.vectorizer = TfidfVectorizer(
                analyzer="char_wb", ngram_range=(2, 5), min_df=1, sublinear_tf=True
            )
        x = self._features([e.text for e in kept], fit=True)
        self.model = LogisticRegression(max_iter=2000, class_weight="balanced").fit(
            x, [e.label for e in kept]
        )
        self.trained_on = len(kept)
        digest = hashlib.sha256("".join(sorted(e.text for e in kept)).encode()).hexdigest()[:10]
        self.version = f"{self.engine}-{self.trained_on}-{digest}"
        return self

    def predict_proba(self, texts: list[str]) -> list[float]:
        if self.model is None:
            raise RuntimeError("Classificatore non addestrato")
        return [float(p[1]) for p in self.model.predict_proba(self._features(texts))]

    def dumps(self) -> bytes:
        import joblib

        buffer = io.BytesIO()
        vectorizer = None if self.engine == "vettori" else self.vectorizer
        joblib.dump(
            {
                "engine": self.engine,
                "model": self.model,
                "vectorizer": vectorizer,
                "version": self.version,
                "trained_on": self.trained_on,
            },
            buffer,
        )
        return buffer.getvalue()

    @classmethod
    def loads(cls, data: bytes) -> Classifier:
        import joblib

        state = joblib.load(io.BytesIO(data))  # noqa: S301 - file prodotto da noi e archiviato per hash
        obj = cls(state["engine"])
        obj.model, obj.version, obj.trained_on = state["model"], state["version"], state["trained_on"]
        obj.vectorizer = state["vectorizer"] if state["engine"] != "vettori" else _embedder()
        return obj


def metrics(truth: list[bool], predicted: list[bool]) -> dict[str, float]:
    tp = sum(1 for t, p in zip(truth, predicted, strict=True) if t and p)
    fp = sum(1 for t, p in zip(truth, predicted, strict=True) if not t and p)
    fn = sum(1 for t, p in zip(truth, predicted, strict=True) if t and not p)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "precisione": round(precision, 3),
        "richiamo": round(recall, 3),
        "f1": round(f1, 3),
        "veri_positivi": tp,
        "falsi_positivi": fp,
        "falsi_negativi": fn,
    }
