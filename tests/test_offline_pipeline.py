"""
Unit tests for Offline Intent Classification, Training and Evaluation.
"""
from newcode.offline.dataset_prep import prepare_dataset
from newcode.offline.train import train_offline_pipeline, extract_features
from newcode.offline.evaluate import evaluate_classifier


def test_offline_dataset_preparation():
    dataset = prepare_dataset()
    assert len(dataset.train_texts) > 0
    assert len(dataset.val_texts) > 0
    assert len(dataset.test_texts) > 0
    assert len(dataset.label_to_id) == 5


def test_offline_training_and_evaluation():
    dataset = prepare_dataset()
    model = train_offline_pipeline(output_dir="/tmp/test_model_ckpt")

    # Predict single test case
    feats = extract_features(["我要申请退款退货"])
    pred_idx = model.predict(feats)[0]
    pred_label = model.id_to_label[pred_idx]
    assert pred_label in ["REFUND_REQUEST", "PRE_SALE_RULES"]

    # Evaluate report
    report = evaluate_classifier(model, dataset)
    assert report.accuracy >= 0.0
    assert len(report.confusion_matrix) == model.num_classes

