# -*- coding: utf-8 -*-
"""
百度贴吧前后端爬虫配置。

后端写入 MongoDB 的字段保持和微博项目一致，方便复用同一套前端展示。
"""

# MongoDB 固定默认写入 test 数据库 test_baidu 集合。
MONGO_URI = "mongodb://localhost:27017"
MONGO_DATABASE = "test"
MONGO_COLLECTION = "test_baidu"

# 用于发现贴吧主题帖的吧名。
FORUM_LIST = [
    "股票",
    "基金",
    "金融",
    "证券",
    "期货",
    "外汇",
    "银行",
    "理财",
    "投资",
    "保险",
    "债券",
    "信托",
    "量化交易",
    "股市",
    "炒股",
    "A股",
    "港股",
    "美股",
    "数字货币",
    "区块链",
]

# 随机轮换贴吧：每抓完一个吧的一页，就从剩余贴吧里随机挑下一个吧继续。
RANDOMIZE_FORUM_ORDER = True

# 正文筛选关键词。主题帖标题或正文命中任意一个才会保存。
KEYWORD_LIST = [
    "保本",
    "稳赚",
    "日赚",
    "区块链",
    "拉人头",
    "限时优惠",
    "返利",
    "理财",
    "众筹",
    "炒股",
    "外汇",
    "期货",
    "原始股",
    "无风险",
]

# 单次点击“爬取”最多扫描多少页。前端暂停后可继续。
MAX_PAGES_PER_FORUM = 100
THREAD_PAGE_SIZE = 30
MAX_THREADS_PER_PAGE = 30
THREAD_SORT = "create"  # create/reply/hot/follow

# 过滤条件。
REQUIRE_TEXT = True
REQUIRE_IMAGES = True

# 请求与图片下载。
DOWNLOAD_DELAY = 0.5
IMAGE_TIMEOUT = 30
TRUST_ENV_PROXY = False
DEFAULT_REQUEST_HEADERS = {
    "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,en-US;q=0.7",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
}

# 本地状态与图片目录。
RESULT_DIR = "result"
PIC_DIR = "pic"
SEEN_IDS_FILE = "seen_ids.txt"
