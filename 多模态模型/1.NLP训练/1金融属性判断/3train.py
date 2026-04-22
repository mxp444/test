"""
训练
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

import pandas as pd
from datasets import Dataset

def load_and_clean_data(csv_path):
    """
    加载 CSV 文件，按列位置提取数据：
    - 第一列作为 text
    - 第二列作为 label
    清洗后返回 HuggingFace Dataset 对象，并打印第一条数据作为预览。
    """
    # 读取 CSV（假设可能有表头，但不依赖列名）
    df = pd.read_csv(csv_path)

    # 确保至少有两列
    if df.shape[1] < 2:
        raise ValueError("CSV 文件必须至少包含两列数据")

    # 按位置提取前两列，并重命名为标准列名
    df = pd.DataFrame({
        'text': df.iloc[:, 0],   # 第一列
        'label': df.iloc[:, 1]   # 第二列
    })

    # 清洗数据
    df = df.dropna(subset=['text'])                # 删除文本为空的行
    df['text'] = df['text'].astype(str)            # 统一转为字符串
    df = df[df['text'].str.strip() != '']          # 删除纯空白文本的行
    df['label'] = df['label'].astype(int)          # 标签转为整数

    # 打印第一条数据作为预览
    if len(df) > 0:
        first_text = df.iloc[0]['text']
        first_label = df.iloc[0]['label']
        print("第一条数据预览：")
        print(f"text: {first_text}")
        print(f"label: {first_label}")
        print("-" * 40)
    else:
        print("警告：清洗后数据为空，无数据可打印。")

    # 返回 Dataset
    return Dataset.from_pandas(df[['text', 'label']])


def safe_tokenize_function(examples, tokenizer):
    """分词函数"""
    texts = [str(text) if text is not None else "" for text in examples["text"]]
    return tokenizer(texts, padding="max_length", truncation=True, max_length=512)


def compute_metrics(eval_pred):
    """评估指标"""
    accuracy = evaluate.load("accuracy")
    precision = evaluate.load("precision")
    recall = evaluate.load("recall")
    f1 = evaluate.load("f1")

    predictions, labels = eval_pred
    predictions = np.argmax(predictions, axis=1)
    return {
        "accuracy": accuracy.compute(predictions=predictions, references=labels)["accuracy"],
        "precision": precision.compute(predictions=predictions, references=labels, average="binary")["precision"],
        "recall": recall.compute(predictions=predictions, references=labels, average="binary")["recall"],
        "f1": f1.compute(predictions=predictions, references=labels, average="binary")["f1"],
    }


# ==================== 主程序入口 ====================
if __name__ == '__main__':
    freeze_support()  # Windows系统必备

    # 设置镜像
    os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'

    # 1. 加载数据
    print("正在加载数据...")
    train_dataset = load_and_clean_data("train.csv")
    val_dataset = load_and_clean_data("val.csv")
    test_dataset = load_and_clean_data("test.csv")

    # 2. 加载模型
    print("正在加载模型...")
    model_name = "hfl/chinese-bert-wwm-ext"
    tokenizer = BertTokenizer.from_pretrained(model_name)
    model = BertForSequenceClassification.from_pretrained(model_name, num_labels=2)

    # 3. 分词处理
    print("正在进行分词处理...")
    train_dataset = train_dataset.map(
        lambda x: safe_tokenize_function(x, tokenizer),
        batched=True
    )
    val_dataset = val_dataset.map(
        lambda x: safe_tokenize_function(x, tokenizer),
        batched=True
    )
    test_dataset = test_dataset.map(
        lambda x: safe_tokenize_function(x, tokenizer),
        batched=True
    )

    # 4. 设置格式
    train_dataset.set_format('torch', columns=['input_ids', 'attention_mask', 'label'])
    val_dataset.set_format('torch', columns=['input_ids', 'attention_mask', 'label'])
    test_dataset.set_format('torch', columns=['input_ids', 'attention_mask', 'label'])

    # 5. 设置训练参数
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

    # 6. 创建Trainer
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=val_dataset,
        compute_metrics=compute_metrics,
        tokenizer=tokenizer,
        callbacks=[EarlyStoppingCallback(early_stopping_patience=5)]
    )

    # 7. 开始训练
    print("开始训练...")
    trainer.train()

    # 8. 测试评估
    test_results = trainer.evaluate(test_dataset)
    print("测试集结果：", test_results)

    # 9. 保存模型
    model_save_path = "./my_finance_bert_wwm"
    trainer.save_model(model_save_path)
    tokenizer.save_pretrained(model_save_path)
    print(f"模型已保存到：{model_save_path}")