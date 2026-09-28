"""
Offline dataset preparation and feature encoding for intent classification.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class DatasetSplit:
    train_texts: list[str]
    train_labels: list[int]
    val_texts: list[str]
    val_labels: list[int]
    test_texts: list[str]
    test_labels: list[int]
    label_to_id: dict[str, int]
    id_to_label: dict[int, str]


SAMPLE_INTENT_DATA: list[tuple[str, str]] = [
    # CHITCHAT (0)
    ("你好在吗", "CHITCHAT"),
    ("早安客服你好", "CHITCHAT"),
    ("谢谢你的帮助", "CHITCHAT"),
    ("辛苦啦客服小助手", "CHITCHAT"),
    ("非常感谢你的解答", "CHITCHAT"),
    ("再见啦谢谢你的帮助", "CHITCHAT"),
    # COMPLAINT_HUMAN (1)
    ("找人工客服处理", "COMPLAINT_HUMAN"),
    ("我要找人工投诉你们", "COMPLAINT_HUMAN"),
    ("服务态度极其恶劣要求投诉", "COMPLAINT_HUMAN"),
    ("转接人工客服", "COMPLAINT_HUMAN"),
    ("叫主管出来处理投诉", "COMPLAINT_HUMAN"),
    ("转人工客服我要投诉你们", "COMPLAINT_HUMAN"),
    # REFUND_REQUEST (2)
    ("我要申请退款", "REFUND_REQUEST"),
    ("商品坏了我要退货退款", "REFUND_REQUEST"),
    ("退钱给我不要了", "REFUND_REQUEST"),
    ("订单申请退款退回", "REFUND_REQUEST"),
    ("退货退款流程怎么走", "REFUND_REQUEST"),
    ("申请退货退款服务", "REFUND_REQUEST"),
    # LOGISTICS_PROGRESS (3)
    ("快递到哪了查询物流", "LOGISTICS_PROGRESS"),
    ("什么时候发货呢催发货", "LOGISTICS_PROGRESS"),
    ("顺丰单号查一下物流进度", "LOGISTICS_PROGRESS"),
    ("包裹还没发货催一下物流", "LOGISTICS_PROGRESS"),
    ("我的快递物流到哪里了", "LOGISTICS_PROGRESS"),
    ("查询快递单号物流信息", "LOGISTICS_PROGRESS"),
    # PRE_SALE_RULES (4)
    ("支持7天无理由退货规则吗", "PRE_SALE_RULES"),
    ("可以开增值税专用发票规则吗", "PRE_SALE_RULES"),
    ("新人优惠券规则可以叠加吗", "PRE_SALE_RULES"),
    ("降价了怎么申请保价退差价规则", "PRE_SALE_RULES"),
    ("售后保修政策规则是什么", "PRE_SALE_RULES"),
    ("保价政策和优惠券规则说明", "PRE_SALE_RULES"),
]


def prepare_dataset(
    data: list[tuple[str, str]] | None = None,
    train_ratio: float = 0.6,
    val_ratio: float = 0.2,
) -> DatasetSplit:
    """
    Prepares a deterministic stratified split of the dataset so that each class
    is represented across train, validation, and test splits.
    Guarantees every class with >= 3 samples has train, validation, and test examples.
    """
    data = data or SAMPLE_INTENT_DATA
    labels = sorted({label for _, label in data})
    label_to_id = {lbl: i for i, lbl in enumerate(labels)}
    id_to_label = {i: lbl for lbl, i in label_to_id.items()}

    by_class: dict[str, list[str]] = {lbl: [] for lbl in labels}
    for text, lbl in data:
        by_class[lbl].append(text)

    train_texts: list[str] = []
    train_labels: list[int] = []
    val_texts: list[str] = []
    val_labels: list[int] = []
    test_texts: list[str] = []
    test_labels: list[int] = []

    for lbl in labels:
        items = by_class[lbl]
        m = len(items)
        lid = label_to_id[lbl]

        if m >= 3:
            # Deterministic stratified split ensuring every class has train, val, and test examples
            n_val = max(1, round(m * val_ratio))
            n_train = max(1, round(m * train_ratio))
            if n_train + n_val >= m:
                n_train = max(1, m - n_val - 1)
            n_test = m - n_train - n_val
            if n_test < 1:
                if n_train > 1:
                    n_train -= 1
                elif n_val > 1:
                    n_val -= 1
                n_test = m - n_train - n_val
        elif m == 2:
            n_train, n_val, n_test = 1, 0, 1
        elif m == 1:
            n_train, n_val, n_test = 1, 0, 0
        else:
            continue

        c_train = items[:n_train]
        c_val = items[n_train:n_train + n_val]
        c_test = items[n_train + n_val:n_train + n_val + n_test]

        train_texts.extend(c_train)
        train_labels.extend([lid] * len(c_train))

        val_texts.extend(c_val)
        val_labels.extend([lid] * len(c_val))

        test_texts.extend(c_test)
        test_labels.extend([lid] * len(c_test))

    return DatasetSplit(
        train_texts=train_texts,
        train_labels=train_labels,
        val_texts=val_texts,
        val_labels=val_labels,
        test_texts=test_texts,
        test_labels=test_labels,
        label_to_id=label_to_id,
        id_to_label=id_to_label,
    )

