# -*- coding: utf-8 -*-
"""
微博搜索爬虫配置。

脚本会自动以运行当天为结束日期，只抓取最近 RECENT_DAYS 天内的微博。

运行:
    python scrpy.py

按键:
    s 暂停
    b 继续
    c 退出
"""

# 请求间隔，单位秒。太快容易被微博限制。
DOWNLOAD_DELAY = 3
REQUEST_TIMEOUT = 10
MAX_RETRY = 3

# 是否读取系统环境变量里的代理配置。
# 当前报错 ProxyError 时通常应保持 False，让 requests 不走系统代理。
TRUST_ENV_PROXY = False

# 每个关键词最多翻多少页。微博搜索通常最多展示 50 页左右。
MAX_PAGES = 50

# 随机交错发现搜索词，避免按 KEYWORD_LIST 顺序先爬完第一个词。
RANDOMIZE_CRAWL_ORDER = True

DEFAULT_REQUEST_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,en-US;q=0.7",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "cookie": "SCF=ApNVkLgzAkBJh4TdVBRQfOBMpojSzroPbVMh1ldO3HGnDaVPf8szLVsXJwb5OnEpZAg38e2Mzn1mCkCgjcCW1Oo.; SUB=_2A25E41NIDeRhGeFI71sU8C7MyT6IHXVngeqArDV8PUNbmtANLUX7kW9NfRmw4KIQt9nuNRB3GU955gcJObykGOHz; SUBP=0033WrSXqPxfM725Ws9jqgMF55529P9D9WW2D5l3HOThWe2YmXPFbl0.5NHD95QNSoB4SK57ehzEWs4DqcjMi--NiK.Xi-2Ri--ciKnRi-zNS0qX1K-7eh5Eentt; ALF=02_1779347480; SINAGLOBAL=3333525641072.579.1776755482737; ULV=1776755482739:1:1:1:3333525641072.579.1776755482737:; PC_TOKEN=0ed7666163; XSRF-TOKEN=WGhQuwsD8cyh3maHg-VQbXAo; WBPSESS=2httqugkf8ww1BZXpvUE9xNJ9nEZrrDyOhtfOWRl1EJR2v5p-Nies-HnM3dwly4l2yqPHlVmZC1JGomfm0OWoP8sHW2yHPYxcaepyjkkf--XBsKfPWCZxLomL8gFoyyMI4zIW8ttAGPMDlK4ceQ9qg==",
}

# 筛选关键词库。爬到的微博正文只要命中其中一个或多个关键词，才会保存到 MongoDB。
# 可以写列表，也可以写 txt 文件路径，txt 中每行一个关键词。
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

# 发现微博用的搜索词。
# 微博搜索页必须有 q 参数，脚本会先用这里的词去搜索，再用 KEYWORD_LIST 做正文筛选。
# 如果设为空列表，则默认沿用 KEYWORD_LIST 作为发现词。
CRAWL_KEYWORD_LIST = []

# 微博类型:
# 0 全部微博，1 原创微博，2 热门微博，3 关注人微博，4 认证用户微博，5 媒体微博，6 观点微博。
WEIBO_TYPE = 0

# 内容筛选:
# 0 不筛选，1 含图片，2 含视频，3 含音乐，4 含短链接。
CONTAIN_TYPE = 1

# 简化版默认不按地区细分；如需地区参数，可填微博搜索支持的 region code。
REGION_CODE = ""

# 自动时间范围:
# 结束日期为运行当天；起始日期为运行当天向前 RECENT_DAYS 天。
# 60 天约等于最近两个月。
RECENT_DAYS = 60

# 按微博发布时间随机丢弃旧微博，让数据库里越新的微博占比越高。
# 规则: 今天发布的微博基本不丢弃；越接近 RECENT_DAYS 天前，丢弃概率越接近此值。
# 例如 0.8 表示 60 天前的微博约 80% 会被丢弃。
MAX_OLD_DROP_RATE = 1.0

# 保留原项目里的阈值配置，当前简单版不做“按天/小时/地区”深度拆分。
FURTHER_THRESHOLD = 46

# MongoDB 固定默认写入 test 数据库 test 集合。
MONGO_URI = "mongodb://localhost:27017"
MONGO_DATABASE = "test"
MONGO_COLLECTION = "test_weibo"

# 本地结果目录。图片会下载到 result/pic，MongoDB 的 pics 字段保存本地绝对路径。
RESULT_DIR = "result"
PIC_DIR = "pic"
IMAGE_TIMEOUT = 30

# 防止重复爬取的本地状态文件。
SEEN_IDS_FILE = "seen_ids.txt"
