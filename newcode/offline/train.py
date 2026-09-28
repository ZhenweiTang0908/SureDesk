"""
Lightweight intent classification model and offline training pipeline.
Implements a fast, dependency-free softmax linear classifier on top of n-gram embedding features.
"""
from __future__ import annotations

import json
import zlib
from pathlib import Path

import numpy as np

from newcode.offline.dataset_prep import DatasetSplit, prepare_dataset


def extract_features(texts: list[str], dim: int = 128) -> np.ndarray:
    """Encodes texts into dense feature vectors using deterministic character and bi-gram hashing."""
    features = np.zeros((len(texts), dim), dtype=np.float32)
    for row, text in enumerate(texts):
        for i in range(len(text)):
            c = text[i]
            features[row, zlib.crc32(c.encode("utf-8")) % dim] += 1.0
            if i > 0:
                bigram = text[i - 1:i + 1]
                features[row, zlib.crc32(bigram.encode("utf-8")) % dim] += 2.0
        norm = np.linalg.norm(features[row])
        if norm > 0:
            features[row] /= norm
    return features


class LightweightIntentClassifier:
    """
    Multinomial Logistic Regression classifier with L2 regularization.
    """

    def __init__(self, feature_dim: int = 128, num_classes: int = 5):
        self.feature_dim = feature_dim
        self.num_classes = num_classes
        self.W = np.zeros((feature_dim, num_classes), dtype=np.float32)
        self.b = np.zeros(num_classes, dtype=np.float32)
        self.id_to_label: dict[int, str] = {}

    def softmax(self, logits: np.ndarray) -> np.ndarray:
        exp_logits = np.exp(logits - np.max(logits, axis=-1, keepdims=True))
        return exp_logits / np.sum(exp_logits, axis=-1, keepdims=True)

    def train(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        epochs: int = 100,
        lr: float = 0.5,
        reg: float = 1e-4,
    ) -> list[float]:
        num_samples = X_train.shape[0]
        losses: list[float] = []

        for epoch in range(epochs):
            logits = np.dot(X_train, self.W) + self.b
            probs = self.softmax(logits)

            # Cross entropy loss
            correct_probs = probs[np.arange(num_samples), y_train]
            loss = -np.mean(np.log(np.clip(correct_probs, 1e-12, 1.0))) + 0.5 * reg * np.sum(self.W ** 2)
            losses.append(float(loss))

            # Gradients
            dlogits = probs.copy()
            dlogits[np.arange(num_samples), y_train] -= 1.0
            dlogits /= num_samples

            dW = np.dot(X_train.T, dlogits) + reg * self.W
            db = np.sum(dlogits, axis=0)

            self.W -= lr * dW
            self.b -= lr * db

        return losses

    def predict(self, X: np.ndarray) -> np.ndarray:
        logits = np.dot(X, self.W) + self.b
        return np.argmax(logits, axis=-1)

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        logits = np.dot(X, self.W) + self.b
        return self.softmax(logits)


DEFAULT_CHECKPOINT_DIR = str(Path(__file__).resolve().parents[2] / "models_checkpoint")


def train_offline_pipeline(
    output_dir: str | Path | None = None,
    dataset: DatasetSplit | None = None,
) -> LightweightIntentClassifier:
    if dataset is None:
        dataset = prepare_dataset()
    X_train = extract_features(dataset.train_texts)
    y_train = np.array(dataset.train_labels)

    model = LightweightIntentClassifier(feature_dim=128, num_classes=len(dataset.label_to_id))
    model.id_to_label = dataset.id_to_label
    model.train(X_train, y_train, epochs=150, lr=0.8)

    # Save checkpoint
    out_path = Path(output_dir) if output_dir is not None else Path(DEFAULT_CHECKPOINT_DIR)
    out_path.mkdir(parents=True, exist_ok=True)
    np.save(out_path / "weights_W.npy", model.W)
    np.save(out_path / "weights_b.npy", model.b)
    with open(out_path / "labels.json", "w", encoding="utf-8") as f:
        json.dump(dataset.id_to_label, f, ensure_ascii=False, indent=2)

    return model

