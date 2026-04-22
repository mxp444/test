"""
训练（多分类自适应版本）
"""

import os
import pandas as pd
import numpy as np
import torch
from transformers import (
    BertTokenizer,
    BertForSequenceClassification,
    Trainer,
    TrainingArguments,
    EarlyStoppingCallback
)
from datasets import Dataset
import evaluate
from multiprocessing import freeze_support
from sklearn.preprocessing import LabelEncoder  # 用于标签映射

def load_and_clean_data(csv_path, label_encoder=None, fit=False):
    """
    加载 CSV 文件，按列位置提取数据：
    - 第一列作为 text
    - 第二列作为 label
    清洗后返回 HuggingFace Dataset 对象，并打印第一条数据作为预览。
    如果 fit=True，则返回 (dataset, label_encoder) 用于训练集拟合编码器；
    否则只返回 dataset，并使用传入的 label_encoder 转换标签。
    """
    df = pd.read_csv(csv_path)

    if df.shape[1] < 2:
        raise ValueError("CSV 文件必须至少包含两列数据")

    # 按位置提取前两列，并重命名为标准列名
    df = pd.DataFrame({
        'text': df.iloc[:, 0],
        'label': df.iloc[:, 1]
    })

    # 清洗
    df = df.dropna(subset=['text'])
    df['text'] = df['text'].astype(str)
    df = df[df['text'].str.strip() != '']

    # 处理标签
    if fit:
        # 训练集：拟合并转换标签
        label_encoder = LabelEncoder()
        df['label'] = label_encoder.fit_transform(df['label'].astype(str))
    else:
        # 验证/测试集：使用已拟合的编码器转换
        if label_encoder is None:
            raise ValueError("验证/测试集必须提供已拟合的 LabelEncoder")
        df['label'] = label_encoder.transform(df['label'].astype(str))

    # 预览
    if len(df) > 0:
        first_text = df.iloc[0]['text']
        first_label = df.iloc[0]['label']
        print("第一条数据预览：")
        print(f"text: {first_text}")
        print(f"label: {first_label}")
        print("-" * 40)

    dataset = Dataset.from_pandas(df[['text', 'label']])
    if fit:
        return dataset, label_encoder
    else:
        return dataset


def safe_tokenize_function(examples, tokenizer):
    texts = [str(text) if text is not None else "" for text in examples["text"]]
    return tokenizer(texts, padding="max_length", truncation=True, max_length=512)


def compute_metrics(eval_pred, num_labels):
    """评估指标（自动适应二分类/多分类）"""
    accuracy = evaluate.load("accuracy")
    precision = evaluate.load("precision")
    recall = evaluate.load("recall")
    f1 = evaluate.load("f1")

    predictions, labels = eval_pred
    predictions = np.argmax(predictions, axis=1)

    # 根据类别数选择 average 模式
    if num_labels == 2:
        avg_mode = "binary"
    else:
        avg_mode = "weighted"  # 或 "macro"，根据需求选择

    return {
        "accuracy": accuracy.compute(predictions=predictions, references=labels)["accuracy"],
        "precision": precision.compute(predictions=predictions, references=labels, average=avg_mode)["precision"],
        "recall": recall.compute(predictions=predictions, references=labels, average=avg_mode)["recall"],
        "f1": f1.compute(predictions=predictions, references=labels, average=avg_mode)["f1"],
    }


if __name__ == '__main__':
    freeze_support()
    os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'

    # 1. 加载训练集，并拟合标签编码器
    print("正在加载训练数据...")
    train_dataset, label_encoder = load_and_clean_data("train.csv", fit=True)

    # 获取类别数
    num_labels = len(label_encoder.classes_)
    print(f"检测到 {num_labels} 个类别：{list(label_encoder.classes_)}")

    # 2. 加载验证集和测试集（使用同一编码器）
    print("正在加载验证数据...")
    val_dataset = load_and_clean_data("val.csv", label_encoder=label_encoder)

    print("正在加载测试数据...")
    test_dataset = load_and_clean_data("test.csv", label_encoder=label_encoder)

    # 3. 加载模型（动态设置 num_labels）
    print("正在加载模型...")
    model_name = "hfl/chinese-bert-wwm-ext"
    tokenizer = BertTokenizer.from_pretrained(model_name)
    model = BertForSequenceClassification.from_pretrained(model_name, num_labels=num_labels)

    # 4. 分词处理
    print("正在进行分词处理...")
    train_dataset = train_dataset.map(lambda x: safe_tokenize_function(x, tokenizer), batched=True)
    val_dataset = val_dataset.map(lambda x: safe_tokenize_function(x, tokenizer), batched=True)
    test_dataset = test_dataset.map(lambda x: safe_tokenize_function(x, tokenizer), batched=True)

    # 5. 设置格式
    train_dataset.set_format('torch', columns=['input_ids', 'attention_mask', 'label'])
    val_dataset.set_format('torch', columns=['input_ids', 'attention_mask', 'label'])
    test_dataset.set_format('torch', columns=['input_ids', 'attention_mask', 'label'])

    # 6. 训练参数
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    LOG_DIR = os.path.join(BASE_DIR, "logs")
    OUTPUT_DIR = os.path.join(BASE_DIR, "finetuned_bert_wwm")
    os.makedirs(LOG_DIR, exist_ok=True)

    training_args = TrainingArguments(
        report_to="none",
        output_dir=OUTPUT_DIR,
        logging_dir=LOG_DIR,
        eval_strategy="epoch",
        save_strategy="epoch",
        learning_rate=1e-5,
        per_device_train_batch_size=16,
        per_device_eval_batch_size=32,
        num_train_epochs=100,
        weight_decay=0.01,
        load_best_model_at_end=True,
        metric_for_best_model="f1",
        save_total_limit=2,
        logging_steps=100,
        fp16=torch.cuda.is_available(),
        dataloader_num_workers=0 if os.name == 'nt' else 4,
    )

    # 7. 创建 Trainer（传递 num_labels 给 compute_metrics）
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=val_dataset,
        compute_metrics=lambda eval_pred: compute_metrics(eval_pred, num_labels),
        tokenizer=tokenizer,
        callbacks=[EarlyStoppingCallback(early_stopping_patience=5)]
    )

    # 8. 开始训练
    print("开始训练...")
    trainer.train()

    # 9. 测试评估
    test_results = trainer.evaluate(test_dataset)
    print("测试集结果：", test_results)

    # 10. 保存模型和标签编码器（以便预测时还原标签）
    model_save_path = "./my_finance_bert_wwm"
    trainer.save_model(model_save_path)
    tokenizer.save_pretrained(model_save_path)

    # 保存标签编码器
    import joblib
    joblib.dump(label_encoder, os.path.join(model_save_path, "label_encoder.pkl"))
    print(f"模型和标签编码器已保存到：{model_save_path}")