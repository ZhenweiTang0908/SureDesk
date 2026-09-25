"""
Offline evaluation for Intent Classifier, computing Accuracy, Confusion Matrix, and F1-score.
"""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np
from newcode.offline.dataset_prep import DatasetSplit, prepare_dataset
from newcode.offline.train import LightweightIntentClassifier, extract_features


@dataclass
class ClassificationReport:
    accuracy: float
    confusion_matrix: list[list[int]]
    precision_by_class: dict[str, float]
    recall_by_class: dict[str, float]
    f1_by_class: dict[str, float]


def evaluate_classifier(model: LightweightIntentClassifier, dataset: DatasetSplit) -> ClassificationReport:
    X_test = extract_features(dataset.test_texts)
    y_test = np.array(dataset.test_labels)

    y_pred = model.predict(X_test)
    num_classes = model.num_classes

    # Confusion matrix
    cm = [[0 for _ in range(num_classes)] for _ in range(num_classes)]
    for true_lbl, pred_lbl in zip(y_test, y_pred):
        cm[true_lbl][pred_lbl] += 1

    accuracy = float(np.mean(y_test == y_pred)) if len(y_test) > 0 else 0.0

    p_dict = {}
    r_dict = {}
    f1_dict = {}

    for c in range(num_classes):
        label_name = model.id_to_label.get(c, str(c))
        tp = cm[c][c]
        fp = sum(cm[r][c] for r in range(num_classes) if r != c)
        fn = sum(cm[c][col] for col in range(num_classes) if col != c)

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

        p_dict[label_name] = precision
        r_dict[label_name] = recall
        f1_dict[label_name] = f1

    return ClassificationReport(
        accuracy=accuracy,
        confusion_matrix=cm,
        precision_by_class=p_dict,
        recall_by_class=r_dict,
        f1_by_class=f1_dict,
    )

