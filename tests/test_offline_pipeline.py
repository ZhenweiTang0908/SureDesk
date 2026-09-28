"""
Unit tests for Offline Intent Classification, Training and Evaluation.
"""
from pathlib import Path

from newcode.offline.dataset_prep import prepare_dataset
from newcode.offline.evaluate import evaluate_classifier
from newcode.offline.train import extract_features, train_offline_pipeline


def test_offline_dataset_preparation():
    dataset = prepare_dataset()
    assert len(dataset.train_texts) > 0
    assert len(dataset.val_texts) > 0
    assert len(dataset.test_texts) > 0
    assert len(dataset.label_to_id) == 5

    # Stratified split: every class must have train, validation, and test examples
    class_ids = set(dataset.label_to_id.values())
    assert set(dataset.train_labels) == class_ids, "Every class must have training examples"
    assert set(dataset.val_labels) == class_ids, "Every class must have validation examples"
    assert set(dataset.test_labels) == class_ids, "Every class must have test examples"

    # Consistency checks
    assert len(dataset.train_texts) == len(dataset.train_labels)
    assert len(dataset.val_texts) == len(dataset.val_labels)
    assert len(dataset.test_texts) == len(dataset.test_labels)

    # Determinism check
    ds_repeat = prepare_dataset()
    assert ds_repeat.train_texts == dataset.train_texts
    assert ds_repeat.val_texts == dataset.val_texts
    assert ds_repeat.test_texts == dataset.test_texts


def test_offline_training_and_evaluation(tmp_path: Path):
    dataset = prepare_dataset()
    ckpt_dir = str(tmp_path / "model_ckpt")
    model = train_offline_pipeline(output_dir=ckpt_dir)

    # Predict single test case
    feats = extract_features(["我要申请退款退货"])
    pred_idx = model.predict(feats)[0]
    pred_label = model.id_to_label[pred_idx]
    assert pred_label == "REFUND_REQUEST"

    # Evaluate report with quality assertions that fail at 0% accuracy
    report = evaluate_classifier(model, dataset)
    assert report.accuracy > 0.0, "Model accuracy must be strictly greater than 0%"
    assert report.accuracy >= 0.7, f"Model accuracy too low: {report.accuracy:.2%}"
    assert len(report.confusion_matrix) == model.num_classes

    # Macro F1 assertion ensuring all classes are predicted reasonably well
    macro_f1 = sum(report.f1_by_class.values()) / len(report.f1_by_class)
    assert macro_f1 >= 0.7, f"Macro F1 too low: {macro_f1:.2%}"
    for label_name, f1 in report.f1_by_class.items():
        assert f1 > 0.0, f"Class '{label_name}' must have non-zero F1 score (got {f1})"


def test_train_offline_pipeline_default_output(tmp_path: Path, monkeypatch):
    """Verify that default output_dir is portable and not tied to developer-specific paths."""
    mock_ckpt = tmp_path / "default_ckpt"
    monkeypatch.setattr("newcode.offline.train.DEFAULT_CHECKPOINT_DIR", str(mock_ckpt))

    model = train_offline_pipeline()
    assert model is not None
    assert (mock_ckpt / "weights_W.npy").exists()
    assert (mock_ckpt / "weights_b.npy").exists()
    assert (mock_ckpt / "labels.json").exists()

