from pymongo import MongoClient
import difflib


def simple_similarity_removal(db, collection, field, threshold):
    """简单相似度去重"""
    # 配置
    client = MongoClient('mongodb://localhost:27017/')
    db = client[db]
    collection = db[collection]

    print("开始基于相似度去重...")

    # 获取所有数据
    all_docs = list(collection.find({}, {field: 1, '_id': 1}))
    total = len(all_docs)

    print(f"总数据量: {total}")

    to_delete = set()

    # 两两比较
    for i in range(total):
        if i in to_delete:
            continue

        doc1 = all_docs[i]
        text1 = doc1.get(field, '')

        if not text1:
            continue

        for j in range(i + 1, total):
            if j in to_delete:
                continue

            doc2 = all_docs[j]
            text2 = doc2.get(field, '')

            if not text2:
                continue

            # 计算相似度
            similarity = difflib.SequenceMatcher(None, text1, text2).ratio()

            if similarity >= threshold:
                print(f"发现相似数据: {doc1['_id']} 和 {doc2['_id']} (相似度: {similarity:.2%})")
                to_delete.add(j)  # 标记后面的为重复

    # 删除重复数据
    if to_delete:
        delete_ids = [all_docs[i]['_id'] for i in to_delete]
        result = collection.delete_many({'_id': {'$in': delete_ids}})
        print(f"\n删除了 {result.deleted_count} 条重复数据")
    else:
        print("没有发现重复数据")

    client.close()


if __name__ == "__main__":
    # simple_similarity_removal(db, collection, field, threshold)
    simple_similarity_removal("weibo", "weibo", "text", 0.7)