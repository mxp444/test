def remove_ns_from_file(input_file, output_file=None):
    """
    删除每行末尾的"ns"及之前的空格

    参数:
        input_file: 输入文件路径
        output_file: 输出文件路径（如果为None，则覆盖原文件）
    """
    if output_file is None:
        output_file = input_file

    # 读取所有行
    with open(input_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    # 处理每一行
    processed_lines = []
    for line in lines:
        # 去除行尾的换行符
        line = line.rstrip('\n')

        # 如果行以"ns"结尾，删除"ns"及之前的空格
        if line.endswith('ns'):
            # 找到最后一个"ns"的位置
            ns_index = line.rfind('ns')
            # 如果"ns"前面有空格，删除到空格前
            if ns_index > 0 and line[ns_index - 1] == ' ':
                line = line[:ns_index - 1]  # 删除空格和ns
            else:
                line = line[:ns_index]  # 只删除ns
        elif line.endswith(' ns'):  # 处理" ns"结尾的情况
            line = line[:-3]  # 删除空格和ns

        processed_lines.append(line)

    # 写入文件
    with open(output_file, 'w', encoding='utf-8') as f:
        for line in processed_lines:
            f.write(line + '\n')

    print(f"处理完成！文件已保存到: {output_file}")


# 使用示例
if __name__ == "__main__":
    input_file = "professional_words.txt"  # 替换为你的文件名
    remove_ns_from_file(input_file)