"""
对原始数据打标签
"""

from pymongo import MongoClient
import time


def quick_labeling():
    """极简打标签函数 - 从无到有添加label字段"""
    # 连接数据库
    client = MongoClient('mongodb://localhost:27017/')
    db = client['weibo']  # 修改为你的数据库名
    collection = db['train']  # 修改为你的集合名

    # 获取所有数据（不管有没有label字段）
    all_data = list(collection.find({"label": {"$exists": False}}).sort('_id', 1))
    total = len(all_data)

    print(f"共找到 {total} 条数据")
    print("=" * 50)
    print("开始打标签 (1=正向, 0=负向)")
    print("=" * 50)

    labeled_count = 0
    for i, doc in enumerate(all_data, 1):
        # 显示进度
        print(f"\n[{i}/{total}]")
        print("-" * 30)

        # 显示内容（假设字段名为'content'，根据你的实际字段名修改）
        content = doc.get('text')
        prefix = "内容: "
        line_width = 100
        # 将内容按每行50字分割
        lines = []
        for i in range(0, len(content), line_width):
            lines.append(content[i:i + line_width])
        # 输出第一行（带前缀）
        if lines:
            print(prefix + lines[0])
            # 输出后续行（无前缀）
            for line in lines[1:]:
                print(line)
        else:
            # 内容为空时只输出前缀（可选）
            print(prefix)
        print("-" * 30)

        # 获取输入
        while True:
            label = input("请输入标签 (1/0, q=退出): ").strip()

            if label == 'q':
                print(f"\n已退出，完成了 {labeled_count} 条")
                client.close()
                return

            if label in ['0', '1']:
                # 添加label字段到数据库
                collection.update_one(
                    {'_id': doc['_id']},
                    {'$set': {
                        'label': int(label),  # 添加label字段
                        'labeled_at': time.time()  # 添加标记时间（可选）
                    }}
                )
                labeled_count += 1
                print(f"✓ 已添加label={label}")
                break
            else:
                print("❌ 只能输入 0 或 1")

    print("\n" + "=" * 50)
    print(f"✅ 完成！共为 {labeled_count} 条数据添加了label字段")

    # 显示统计
    pos = collection.count_documents({'label': 1})
    neg = collection.count_documents({'label': 0})
    print(f"正向(1): {pos} 条")
    print(f"负向(0): {neg} 条")
    print("=" * 50)

    client.close()


if __name__ == "__main__":
    quick_labeling()