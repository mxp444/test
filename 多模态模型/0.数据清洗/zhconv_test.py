import zhconv

# 繁体转简体（最常用）
text = "這是一段繁體中文文本。"
simplified = zhconv.convert(text, 'zh-cn')
print(simplified)  # 输出：这是一段简体中文文本。