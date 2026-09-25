"""
Offline dataset preparation and feature encoding for intent classification.
"""
from __future__ import annotations

import re
from typing import Any
from dataclasses import dataclass
import numpy as np


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
    ("早安客服", "CHITCHAT"),
    ("谢谢你的帮助", "CHITCHAT"),
    ("再见啦", "CHITCHAT"),
    # COMPLAINT_HUMAN (1)
    ("找人工客服", "COMPLAINT_HUMAN"),
    ("我要投诉你们", "COMPLAINT_HUMAN"),
    ("服务态度极其恶劣", "COMPLAINT_HUMAN"),
    ("叫你们主管出来", "COMPLAINT_HUMAN"),
    # REFUND_REQUEST (2)
    ("我要申请退款", "REFUND_REQUEST"),
    ("商品坏了我要退货", "REFUND_REQUEST"),
    ("退钱给我不要了", "REFUND_REQUEST"),
    ("订单退款退回", "REFUND_REQUEST"),
    # LOGISTICS_PROGRESS (3)
    ("快递到哪了", "LOGISTICS_PROGRESS"),
    ("什么时候发货呢", "LOGISTICS_PROGRESS"),
    ("顺丰单号查一下进度", "LOGISTICS_PROGRESS"),
    ("包裹还没发货催一下", "LOGISTICS_PROGRESS"),
    # PRE_SALE_RULES (4)
    ("支持7天无理由退货吗", "PRE_SALE_RULES"),
    ("可以开增值税专用发票吗", "PRE_SALE_RULES"),
    ("新人优惠券可以叠加吗", "PRE_SALE_RULES"),
    ("降价了怎么申请保价退差价", "PRE_SALE_RULES"),
]


def prepare_dataset(
    data: list[tuple[str, str]] | None = None,
    train_ratio: float = 0.6,
    val_ratio: float = 0.2,
) -> DatasetSplit:
    data = data or SAMPLE_INTENT_DATA
    labels = sorted(list(set(label for _, label in data)))
    label_to_id = {lbl: i for i, lbl in enumerate(labels)}
    id_to_label = {i: lbl for lbl, i in label_to_id.items()}

    texts = [item[0] for item in data]
    label_ids = [label_to_id[item[1]] for item in data]

    # Split indices deterministically
    n = len(data)
    n_train = int(n * train_ratio)
    n_val = int(n * val_ratio)

    train_texts = texts[:n_train]
    train_labels = label_ids[:n_train]

    val_texts = texts[n_train:n_train + n_val]
    val_labels = label_ids[n_train:n_train + n_val]

    test_texts = texts[n_train + n_val:]
    test_labels = label_ids[n_train + n_val:]

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

