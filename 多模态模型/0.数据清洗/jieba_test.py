import jieba

# 精确模式 (最常用)
text = "#梓渝演唱会的上座率#桃花气息最重的网红，争议很大，已经进入高峰期，该注意保本保息了！"
seg_list = jieba.lcut_for_search(text)  # lcut 直接返回列表
print(seg_list)
# 输出: ['我', '来到', '北京', '清华大学']