from multistop import Stopwords

# 初始化中文停用词
sw = Stopwords()
sw.setlang(lang='chinese')
weibo_stopwords = [
            '转发', '微博', '网页链接', '图片', '评论',
            '赞', '分享', '收藏', '回复', '哈哈哈', '呵呵'
        ]
for word in weibo_stopwords:
    sw.add(word)