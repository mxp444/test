import argparse
import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split


def split_csv(input_file, train_file, test_file, val_file, seed=42):
    """
    将 CSV 文件按 8:1:1 的比例随机划分为训练、测试、验证集。
    """
    # 读取 CSV 文件
    df = pd.read_csv(input_file)

    # 先划分出训练集（80%）和临时集（20%）
    train_df, temp_df = train_test_split(df, test_size=0.2, random_state=seed)

    # 再将临时集平均分为测试集和验证集（各占10%）
    test_df, val_df = train_test_split(temp_df, test_size=0.5, random_state=seed)

    # 保存文件
    train_df.to_csv(train_file, index=False)
    test_df.to_csv(test_file, index=False)
    val_df.to_csv(val_file, index=False)

    print(f"划分完成：")
    print(f"  训练集: {len(train_df)} 条 -> {train_file}")
    print(f"  测试集: {len(test_df)} 条 -> {test_file}")
    print(f"  验证集: {len(val_df)} 条 -> {val_file}")


if __name__ == "__main__":
    split_csv("1.csv", "train.csv", "test.csv", "val.csv", 42)