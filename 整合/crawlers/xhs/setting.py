# -*- coding: utf-8 -*-
import os
from pathlib import Path

from dotenv import load_dotenv


PROJECT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PROJECT_DIR
load_dotenv(PROJECT_ROOT / ".env")

# 小红书 cookies 优先从根目录 .env 的 COOKIES 读取，也可以直接在这里覆盖。
COOKIES = os.getenv("COOKIES", "")

# 发现关键词。可以写列表，也可以改成 txt 文件路径，文件里每行一个关键词。
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

# 每个关键词最多抓多少条搜索结果。
LIMIT_PER_KEYWORD = 100

# 像微博项目一样随机交错抓不同搜索词，避免一个词一次性跑到底。
RANDOMIZE_CRAWL_ORDER = True

# 每个搜索词最多翻多少页；小红书搜索接口每页约 20 条。
MAX_PAGES = 5

# 本地去重文件，跨轮记录已成功入库的 note_id。
SEEN_IDS_FILE = "seen_ids.txt"

# 排序：0 综合，1 最新，2 最多点赞，3 最多评论，4 最多收藏。
SORT_TYPE = 0

# 笔记类型：0 不限，1 视频，2 图文。默认图文，便于保存图片。
NOTE_TYPE = 2

# 时间：0 不限，1 一天内，2 一周内，3 半年内。
NOTE_TIME = 0

# 范围：0 不限，1 已看过，2 未看过，3 已关注。
NOTE_RANGE = 0

# 请求间隔，单位秒。
DOWNLOAD_DELAY = 1.0
BATCH_SIZE = 1
FETCH_DETAIL = True
PROXY = None

# MongoDB 固定默认写入 test.test_xhs，字段格式对齐微博项目。
MONGO_URI = "mongodb://localhost:27017"
MONGO_DATABASE = "test"
MONGO_COLLECTION = "test_xhs"

# 图片下载到本地，MongoDB 的 pics 字段保存本地绝对路径，前端经 /media 预览。
DOWNLOAD_IMAGES = True
REQUIRE_IMAGES = True
SAVE_VIDEO_NOTES = False
RESULT_DIR = "result"
PIC_DIR = "pic"
