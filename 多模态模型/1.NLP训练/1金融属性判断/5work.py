"""
运用模型对整个数据库打多标签（Top-4）
"""

import torch
import numpy as np
import joblib
import pymongo
from datetime import datetime
from tqdm import tqdm
from transformers import BertTokenizer, BertForSequenceClassification

# ==================== 1. 连接MongoDB ====================
client = pymongo.MongoClient("mongodb://localhost:27017/")
db = client["weibo"]  # 替换为你的数据库名
collection = db["weibo"]  # 替换为你的集合名

# ==================== 2. 加载模型、分词器和标签编码器 ====================
model_dir = "./my_finance_bert_wwm"  # 模型保存路径

print("正在加载模型...")
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
tokenizer = BertTokenizer.from_pretrained(model_dir)
model = BertForSequenceClassification.from_pretrained(model_dir)
model.to(device)
model.eval()
label_encoder = joblib.load(f"{model_dir}/label_encoder.pkl")
print(f"模型加载成功，使用设备：{device}")
print(f"标签类别：{list(label_encoder.classes_)}")


# ==================== 3. 定义预测函数（返回Top-4） ====================
def predict_topk(texts, k=4):
    """
    对文本列表进行预测，返回每条文本的 top-k 标签和置信度
    """
    inputs = tokenizer(
        texts,
        padding=True,
        truncation=True,
        max_length=512,
        return_tensors="pt"
    )
    inputs = {k: v.to(device) for k, v in inputs.items()}

    with torch.no_grad():
        outputs = model(**inputs)
        logits = outputs.logits
        probs = torch.softmax(logits, dim=-1).cpu().numpy()  # (batch_size, num_labels)

    # 取 top-k 索引和概率
    topk_indices = np.argsort(-probs, axis=-1)[:, :k]  # 降序取前k个
    topk_probs = np.take_along_axis(probs, topk_indices, axis=-1)

    # 将索引转换为原始标签
    batch_labels = []
    for indices in topk_indices:
        labels = label_encoder.inverse_transform(indices)  # 返回字符串数组
        # 可选：将字符串转为整数（如果原始标签是数字）
        labels = [int(l) if l.isdigit() else l for l in labels]
        batch_labels.append(labels)

    return batch_labels, topk_probs


# ==================== 4. 查询待预测的数据 ====================
# 建议只处理还没有 top-4 标签的数据（避免重复处理）
# query = {
#     "label_1": {"$exists": False}  # 如果还没有 label_1 字段则处理
# }
# 如果需要强制重新预测所有数据，可注释上一行并使用空查询
query = {}

print("正在查询MongoDB...")
total_count = collection.count_documents(query)
print(f"找到 {total_count} 条待预测的数据")

# ==================== 5. 批量预测并更新 ====================
batch_size = 100
success_count = 0
error_count = 0
stats = {}  # 用于统计各类别出现次数

with tqdm(total=total_count, desc="预测进度") as pbar:
    for i in range(0, total_count, batch_size):
        try:
            # 读取一批数据
            batch = list(collection.find(query).skip(i).limit(batch_size))
            if not batch:
                break

            # 提取文本字段（根据实际情况调整字段名）
            texts = []
            valid_docs = []
            for doc in batch:
                # 尝试多个可能的文本字段
                text = doc.get("processed_result_text2")
                if text and isinstance(text, str) and text.strip():
                    texts.append(text.strip())
                    valid_docs.append(doc)
                else:
                    # 无有效文本，标记为无效
                    collection.update_one(
                        {"_id": doc["_id"]},
                        {"$set": {
                            "label_1": -1,
                            "confidence_1": 0,
                            "prediction_error": "empty_text",
                            "prediction_time": datetime.now()
                        }}
                    )

            if not texts:
                pbar.update(len(batch))
                continue

            # 批量预测
            try:
                batch_labels, batch_probs = predict_topk(texts, k=4)
            except Exception as e:
                print(f"\n预测批次出错: {e}")
                # 降级：标记为错误
                for doc in valid_docs:
                    collection.update_one(
                        {"_id": doc["_id"]},
                        {"$set": {
                            "label_1": -2,
                            "confidence_1": 0,
                            "prediction_error": str(e)[:200],
                            "prediction_time": datetime.now()
                        }}
                    )
                pbar.update(len(batch))
                error_count += len(batch)
                continue

            # 更新数据库
            for doc, labels, probs in zip(valid_docs, batch_labels, batch_probs):
                try:
                    update_data = {
                        "prediction_time": datetime.now(),
                        "prediction_model": "bert_wwm_finance"
                    }
                    # 添加 top-4 标签和置信度
                    for j, (label, prob) in enumerate(zip(labels, probs), start=1):
                        update_data[f"label_{j}"] = label
                        update_data[f"confidence_{j}"] = float(prob)

                    collection.update_one(
                        {"_id": doc["_id"]},
                        {"$set": update_data}
                    )

                    # 统计（仅统计第一标签）
                    first_label = str(labels[0])
                    stats[first_label] = stats.get(first_label, 0) + 1

                    success_count += 1
                except Exception as e:
                    error_count += 1
                    print(f"\n更新文档失败 {doc['_id']}: {e}")

            pbar.update(len(batch))

        except Exception as e:
            print(f"\n批次处理出错: {e}")
            error_count += len(batch)
            pbar.update(len(batch))

# ==================== 6. 输出统计结果 ====================
print("\n" + "=" * 50)
print("✅ 预测完成！")
print(f"成功处理: {success_count} 条")
print(f"失败: {error_count} 条")
print("各类别出现次数（按第一标签统计）:")
for label, count in sorted(stats.items(), key=lambda x: int(x[0]) if x[0].isdigit() else x[0]):
    print(f"  类别 {label}: {count} 条")
print("=" * 50)

# ==================== 7. 查看部分预测结果示例 ====================
print("\n📊 预测结果示例（随机抽取5条）:")
pipeline = [{"$match": {"label_1": {"$exists": True}}}, {"$sample": {"size": 5}}]
examples = collection.aggregate(pipeline)
for doc in examples:
    text = doc.get("content") or doc.get("text") or doc.get("processed_result") or ""
    print(f"- 文本预览: {text[:100]}...")
    for j in range(1, 5):
        label = doc.get(f"label_{j}")
        conf = doc.get(f"confidence_{j}")
        if label is not None:
            print(f"  Top-{j}: 类别 {label} (置信度: {conf:.4f})")
    print()