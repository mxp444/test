from pymongo import MongoClient
import random


def simple_random_copy():
    """简单随机抽取500条数据"""
    # 连接数据库
    client = MongoClient('mongodb://localhost:27017/')
    db = client['weibo']  # weibo数据库

    # 源集合和目标集合
    source = db['weibo']  # weibo集合
    target = db['train']  # test集合

    # 获取所有数据
    all_data = list(source.find({}))
    total = len(all_data)

    print(f"源集合共有 {total} 条数据")

    sample_size = 500

    # 随机抽取
    sample_data = random.sample(all_data, sample_size)

    # 清空目标集合（可选）
    target.delete_many({})

    # 插入数据到test集合
    if sample_data:
        # 移除_id，让MongoDB自动生成新的_id
        for doc in sample_data:
            doc.pop('_id', None)

        result = target.insert_many(sample_data)
        print(f"成功插入 {len(result.inserted_ids)} 条数据到test集合")

    client.close()


if __name__ == "__main__":
    simple_random_copy()