"""
将整个打好标签的数据库过滤出label_1不是0或1的数据（即金融属性数据）
"""

import pymongo
from datetime import datetime
from tqdm import tqdm
import hashlib

# 连接数据库
source_client = pymongo.MongoClient("mongodb://localhost:27017/")
source_db = source_client["weibo"]
source_collection = source_db["weibo"]

target_client = pymongo.MongoClient("mongodb://localhost:27017/")
target_db = target_client["weibo"]
target_collection = target_db["filter"]  # 目标集合，可根据需要改名

# 清空目标集合（重新开始）
print("清空目标集合...")
target_collection.drop()

# 查询条件：label_1 不是0也不是1
query = {"label_1": {"$nin": [0, 1]}}
total_count = source_collection.count_documents(query)
print(f"找到 {total_count} 条 label_1 不为 0/1 的数据")

batch_size = 500
success_count = 0

with tqdm(total=total_count, desc="筛选进度") as pbar:
    for i in range(0, total_count, batch_size):
        batch = list(source_collection.find(query).skip(i).limit(batch_size))

        docs_to_insert = []
        for doc in batch:
            # 保存原始_id
            original_id = doc['_id']

            # 复制文档（去掉原来的_id）
            new_doc = {k: v for k, v in doc.items() if k != '_id'}

            # 添加必要字段
            new_doc['original_id'] = original_id
            new_doc['filtered_at'] = datetime.now()

            # 可选：添加内容哈希用于去重
            content = doc.get('content') or doc.get('text') or ''
            new_doc['content_hash'] = hashlib.md5(content.encode()).hexdigest()

            docs_to_insert.append(new_doc)

        if docs_to_insert:
            target_collection.insert_many(docs_to_insert)
            success_count += len(docs_to_insert)

        pbar.update(len(batch))

# 创建索引
print("\n正在创建索引...")
target_collection.create_index([("filtered_at", pymongo.DESCENDING)])
target_collection.create_index([("original_id", pymongo.ASCENDING)], unique=True)
target_collection.create_index([("label_1", pymongo.ASCENDING)])  # 按主要标签索引
target_collection.create_index([("prediction_confidence", pymongo.DESCENDING)])
print("索引创建完成")

print(f"\n✅ 成功插入 {success_count} 条数据到 filter 集合！")

# 验证
final_count = target_collection.count_documents({})
print(f"filter 集合现在有 {final_count} 条数据")