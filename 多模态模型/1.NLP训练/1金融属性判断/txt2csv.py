import csv
import sys


def process_txt_to_csv(input_txt_path, output_csv_path):
    """
    将指定格式的txt文件转换为csv文件
    规则：每行最后一个逗号前为文本，忽略文本前三个字符；最后一个逗号后为标签数字
    """
    with open(input_txt_path, 'r', encoding='utf-8') as txt_file, \
            open(output_csv_path, 'w', newline='', encoding='utf-8-sig') as csv_file:

        writer = csv.writer(csv_file)
        writer.writerow(['text', 'label'])  # 写入表头

        for line_num, line in enumerate(txt_file, start=1):
            line = line.strip()
            if not line:
                continue  # 跳过空行

            # 找到最后一个逗号的位置
            last_comma = line.rfind(',')
            if last_comma == -1:
                print(f"警告：第{line_num}行格式错误，已跳过：{line[:50]}...")
                continue

            text_part = line[:last_comma]  # 逗号前的部分
            label_part = line[last_comma + 1:]  # 逗号后的部分

            # 检查标签是否为数字（可选）
            if not label_part.isdigit():
                print(f"警告：第{line_num}行标签非数字，已跳过：{label_part}")
                continue

            # 忽略文本部分的前三个字符
            if len(text_part) >= 2:
                processed_text = text_part[2:]
            else:
                processed_text = text_part  # 不足三个字符则保留原样

            writer.writerow([processed_text, label_part])

    print(f"处理完成！结果已保存至：{output_csv_path}")


if __name__ == "__main__":

    process_txt_to_csv("1.txt", "1.csv")