# -*- coding: utf-8 -*-

BOT_NAME = 'weibo'
SPIDER_MODULES = ['weibo.spiders']
NEWSPIDER_MODULE = 'weibo.spiders'
COOKIES_ENABLED = False
TELNETCONSOLE_ENABLED = False
LOG_LEVEL = 'ERROR'
# 访问完一个页面再访问下一个时需要等待的时间，默认为10秒
DOWNLOAD_DELAY = 2
DEFAULT_REQUEST_HEADERS = {
    'Accept':
    'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8,en-US;q=0.7',
    'cookie': "SCF=AjqU4pTncF17I93rxuLKsbwiUmPYTTthsT4AwClhRihhi0VueTJjKLDrSBLRxKGoYOwD1vT6kDOGHcxjfMZEQkA.; SINAGLOBAL=3246657399675.5254.1772363437207; ULV=1772711204199:2:2:2:6170617061724.654.1772711204194:1772363437216; PC_TOKEN=de282b9b34; ALF=1776255269; SUB=_2A25Es4R1DeRhGeFI71sU8C7MyT6IHXVnsJm9rDV8PUJbkNANLWTdkW1NfRmw4DBZvbxrXFzQ-LqbdwT1m5g77RU0; SUBP=0033WrSXqPxfM725Ws9jqgMF55529P9D9WW2D5l3HOThWe2YmXPFbl0.5JpX5KMhUgL.FoMcSh.feh57eoz2dJLoIp7LxKML1KBLBKnLxKqL1hnLBoMNSoB4SK57ehzE; XSRF-TOKEN=6ljjvqG8XDz2Z6jbyqoP0yDj; WBPSESS=2httqugkf8ww1BZXpvUE9xNJ9nEZrrDyOhtfOWRl1EJR2v5p-Nies-HnM3dwly4lLiFXK-HJD4M1BZawiRMTFm2tmo0zP5-URnYYOAnrVV6bFM2rKWmyC-MtdOhxklLTDbrua5Bp3--iVcutZzjP2w=="
}
ITEM_PIPELINES = {
    'weibo.pipelines.DuplicatesPipeline': 300,
    'weibo.pipelines.CsvPipeline': 301,
    #'weibo.pipelines.MysqlPipeline': 302,
    'weibo.pipelines.MyImagesPipeline': 303,
    'weibo.pipelines.MongoPipeline': 304,

    # 'weibo.pipelines.MyVideoPipeline': 305
}
# 要搜索的关键词列表，可写多个, 值可以是由关键词或话题组成的列表，也可以是包含关键词的txt文件路径，
# 如'keyword_list.txt'，txt文件中每个关键词占一行

# import pandas as pd
# def read_and_combine_columns(file_path):
#     all_words = []
#     try:
#         # 读取两个工作表
#         df_neg = pd.read_excel(file_path, sheet_name='negative', usecols=[0],)
#         df_pos = pd.read_excel(file_path, sheet_name='positive', usecols=[0],)
#         # 提取数据并合并
#         neg_words = df_neg.iloc[:, 0].dropna().tolist()
#         pos_words = df_pos.iloc[:, 0].dropna().tolist()
#         # 转换为字符串并去除空格
#         neg_words = [str(w).strip() for w in neg_words]
#         pos_words = [str(w).strip() for w in pos_words]
#         # 合并列表
#         all_words = neg_words + pos_words
#     except Exception as e:
#         print(f"读取文件出错: {e}")
#     return all_words
# all_words = read_and_combine_columns('words/Chinese_financial_sentiment_dictionary-master/financial_sentiment.xlsx')
with open('words/professional_words/professional_words.txt', 'r', encoding='utf-8') as f:
    lines = f.readlines()
lines = [line.strip() for line in lines]
# KEYWORD_LIST = lines  # 或者 KEYWORD_LIST = 'keyword_list.txt'
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
    "无风险"
]
print(KEYWORD_LIST)
# 要搜索的微博类型，0代表搜索全部微博，1代表搜索全部原创微博，2代表热门微博，3代表关注人微博，4代表认证用户微博，5代表媒体微博，6代表观点微博
WEIBO_TYPE = 0
# 筛选结果微博中必需包含的内容，0代表不筛选，获取全部微博，1代表搜索包含图片的微博，2代表包含视频的微博，3代表包含音乐的微博，4代表包含短链接的微博
CONTAIN_TYPE = 1
# 筛选微博的发布地区，精确到省或直辖市，值不应包含“省”或“市”等字，如想筛选北京市的微博请用“北京”而不是“北京市”，想要筛选安徽省的微博请用“安徽”而不是“安徽省”，可以写多个地区，
# 具体支持的地名见region.py文件，注意只支持省或直辖市的名字，省下面的市名及直辖市下面的区县名不支持，不筛选请用“全部”
REGION = ['全部']
# 搜索的起始日期，为yyyy-mm-dd形式，搜索结果包含该日期
START_DATE = '2025-1-1'
# 搜索的终止日期，为yyyy-mm-dd形式，搜索结果包含该日期
END_DATE = '2025-12-31'
# 进一步细分搜索的阈值，若结果页数大于等于该值，则认为结果没有完全展示，细分搜索条件重新搜索以获取更多微博。数值越大速度越快，也越有可能漏掉微博；数值越小速度越慢，获取的微博就越多。
# 建议数值大小设置在40到50之间。
FURTHER_THRESHOLD = 46
# 图片文件存储路径
IMAGES_STORE = './'
# 视频文件存储路径
FILES_STORE = './'
# 配置MongoDB数据库
MONGO_URI = 'localhost'  # MongoDB 连接地址
# 配置MySQL数据库，以下为默认配置，可以根据实际情况更改，程序会自动生成一个名为weibo的数据库，如果想换其它名字请更改MYSQL_DATABASE值
# MYSQL_HOST = 'localhost'
# MYSQL_PORT = 3306
# MYSQL_USER = 'root'
# MYSQL_PASSWORD = '123456'
# MYSQL_DATABASE = 'weibo'
