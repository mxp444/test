"""
对text字段做预处理，新增去标签
"""

from multistop import Stopwords
from pymongo import MongoClient, UpdateOne
import time
import jieba
import re
import html
import zhconv

def clean_weibo_text(text):
    """清洗微博文本（移除HTML、转义字符、特殊符号等）"""
    if not text or not isinstance(text, str):
        return ""

    # 1. 处理HTML转义字符
    text = html.unescape(text)

    # 2. 去除HTML标签
    text = re.sub(r'<[^>]+>', '', text)

    # 3. 去除特殊符号和表情（保留有意义的内容）
    # 保留中英文、数字、空格
    text = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9\s]', '', text)

    # 4. 去除多余空白
    text = re.sub(r'\s+', ' ', text)

    # 5. 去除开头结尾的空白
    text = text.strip()

    return text

class FieldProcessor:
    def __init__(self, connection_string='mongodb://localhost:27017/'):
        self.client = MongoClient(connection_string)
        self.sw = Stopwords()
        self.sw.setlang(lang='chinese')

    def add_processed_field(self, database, collection_name):
        """
        读取每条数据的特定字段，处理后添加为新字段
        """
        db = self.client[database]
        collection = db[collection_name]

        # 只读取需要的字段，提高效率
        cursor = collection.find({}).sort([('$natural', 1)])  # 按存储顺序

        batch = []
        batch_size = 100
        processed = 0

        for doc in cursor:
            # 处理数据并生成新字段
            new_field_value = self.process_document(doc)

            # 准备更新：添加新字段
            batch.append(
                UpdateOne(
                    {'_id': doc['_id']},
                    {'$set': {'processed_result_text2': new_field_value}}
                )
            )

            # 批量执行
            if len(batch) >= batch_size:
                result = collection.bulk_write(batch)
                processed += len(batch)
                print(f"已处理 {processed} 条记录")
                batch = []

        # 处理最后一批
        if batch:
            collection.bulk_write(batch)
            processed += len(batch)

        print(f"完成！共添加 {processed} 个新字段")

    def process_document(self, doc):
        """
        根据文档的现有字段计算新值
        返回要添加的新字段的值
        """
        # 获取原始文本，假设字段名为 'topics'
        text = doc.get("text", "")
        if not isinstance(text, str):
            text = ""

        # ===== 新增：移除所有 #...# 标签（包括标签内容和标签符号）=====
        text = re.sub(r'#([^#]+)#', '', text)

        # 对剩余文本进行常规清洗
        text = clean_weibo_text(text)

        # 分词
        seg_list = jieba.lcut(text)

        # 去除停用词
        seg_list = [word for word in seg_list if not self.sw.contains(word)]

        # 拼接结果（用空格连接）
        result = " ".join(seg_list)

        # 转换为简体中文（原脚本第二个参数有误，修正为 'zh-cn'）
        result = zhconv.convert(result, 'zh-cn')

        return result.rstrip()

    def close(self):
        self.client.close()


if __name__ == '__main__':
    processor = FieldProcessor()
    try:
        processor.add_processed_field('weibo', 'weibo')
    finally:
        processor.close()