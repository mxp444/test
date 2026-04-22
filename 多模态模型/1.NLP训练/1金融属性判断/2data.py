"""
划分数据集
"""

import pandas as pd
import pymongo
from sklearn.model_selection import train_test_split

# 1. 从MongoDB读取已标注的数据
client = pymongo.MongoClient("mongodb://localhost:27017/")
db = client["weibo"]
collection = db["train"]

# 假设你已经为部分数据标注了 'finance_label' 字段
data = list(collection.find({"label": {"$exists": True}}))
df = pd.DataFrame([{"text": d["processed_result_text"], "label": d["label"]} for d in data])

# 2. 划分训练集、验证集、测试集（70/15/15）
train_df, temp_df = train_test_split(df, test_size=0.3, random_state=42)
val_df, test_df = train_test_split(temp_df, test_size=0.5, random_state=42)

# 3. 保存为CSV
train_df.to_csv("train.csv", index=False, encoding="utf-8")
val_df.to_csv("val.csv", index=False, encoding="utf-8")
test_df.to_csv("test.csv", index=False, encoding="utf-8")
print(f"训练集：{len(train_df)}条，验证集：{len(val_df)}条，测试集：{len(test_df)}条")