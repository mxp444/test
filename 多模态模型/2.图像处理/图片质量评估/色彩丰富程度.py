import cv2
import numpy as np
from skimage import exposure, color
import math

class Color_richness():

    def image_quality_score(self, image_path, verbose=False):
        """
        基于HSV、亮度和对比度对图片进行综合质量打分

        Parameters:
        -----------
        image_path : str
            图片文件路径
        verbose : bool
            是否返回详细分数组件

        Returns:
        --------
        score : float
            综合质量得分 (0-100)
        details : dict (optional)
            如果verbose=True，返回各维度详细分数
        """

        # 读取图片
        img = cv2.imread(image_path)
        if img is None:
            raise ValueError(f"无法读取图片: {image_path}")

        # BGR转RGB
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

        # 转换为HSV色彩空间
        img_hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

        # 分离HSV通道
        h, s, v = cv2.split(img_hsv)

        # ==================== 1. 色彩丰富度评分 (0-30分) ====================

        # 色调丰富度：统计色调通道的直方图分布
        h_hist = cv2.calcHist([h], [0], None, [180], [0, 180])
        h_hist_normalized = h_hist / h_hist.sum()

        # 熵值越高，色调分布越均匀，色彩越丰富
        h_entropy = -np.sum(h_hist_normalized * np.log2(h_hist_normalized + 1e-10))
        # 归一化到0-15分（180个bin的最大熵约为7.5，乘以2映射到15分）
        hue_score = min(15, h_entropy * 2)

        # 饱和度丰富度：计算饱和度的平均值和标准差
        s_mean = np.mean(s) / 255.0  # 归一化0-1
        s_std = np.std(s) / 255.0

        # 饱和度评分：中等偏上的饱和度得分高，过高或过低都扣分
        # 理想饱和度范围0.3-0.7
        if 0.3 <= s_mean <= 0.7:
            saturation_mean_score = 7.5  # 满分7.5
        else:
            # 偏离理想区间越远分数越低
            deviation = min(abs(s_mean - 0.3), abs(s_mean - 0.7))
            saturation_mean_score = max(0, 7.5 * (1 - deviation * 2))

        # 饱和度标准差高表示色彩层次丰富
        saturation_std_score = min(7.5, s_std * 15)

        saturation_score = saturation_mean_score + saturation_std_score

        # 色彩丰富度总分 (30分)
        color_richness_score = hue_score + saturation_score

        # ==================== 2. 亮度评分 (0-30分) ====================

        # 计算亮度通道的统计信息
        v_mean = np.mean(v) / 255.0  # 归一化0-1

        # 理想亮度范围：0.4-0.7（中等偏亮）
        if 0.4 <= v_mean <= 0.7:
            brightness_score = 20  # 基础分
        elif v_mean < 0.4:
            # 太暗：线性扣分
            brightness_score = 20 * (v_mean / 0.4)
        else:
            # 太亮：线性扣分
            brightness_score = 20 * ((1 - v_mean) / 0.3)

        # 检查亮度直方图是否过曝或欠曝
        v_hist = cv2.calcHist([v], [0], None, [256], [0, 256])
        v_hist_normalized = v_hist / v_hist.sum()

        # 计算暗部（0-50）和亮部（200-255）的像素比例
        dark_ratio = np.sum(v_hist_normalized[:51])
        bright_ratio = np.sum(v_hist_normalized[200:])

        # 过曝或欠曝惩罚
        if dark_ratio > 0.3:
            brightness_score -= 5 * (dark_ratio - 0.3) * 2
        if bright_ratio > 0.3:
            brightness_score -= 5 * (bright_ratio - 0.3) * 2

        # 确保亮度分在0-30之间
        brightness_score = np.clip(brightness_score, 0, 30)

        # ==================== 3. 对比度评分 (0-40分) ====================

        # 方法1：基于亮度通道的标准差
        v_std = np.std(v) / 255.0
        contrast_std_score = min(20, v_std * 40)  # 标准差0.5对应20分

        # 方法2：基于直方图的动态范围
        # 计算直方图的百分位数
        v_flat = v.flatten()
        p5 = np.percentile(v_flat, 5) / 255.0  # 5%分位
        p95 = np.percentile(v_flat, 95) / 255.0  # 95%分位
        dynamic_range = p95 - p5

        # 理想动态范围0.4-0.8
        if 0.4 <= dynamic_range <= 0.8:
            dynamic_range_score = 15
        else:
            dynamic_range_score = 15 * (1 - abs(dynamic_range - 0.6) / 0.6)

        # 方法3：使用RMS对比度（均方根对比度）
        # 计算图像的标准差，除以平均亮度得到相对对比度
        if v_mean > 0:
            rms_contrast = v_std / v_mean
        else:
            rms_contrast = 0

        rms_score = min(5, rms_contrast * 10)

        contrast_score = contrast_std_score + dynamic_range_score + rms_score
        contrast_score = np.clip(contrast_score, 0, 40)

        # ==================== 4. 综合评分 ====================

        total_score = color_richness_score + brightness_score + contrast_score

        # 归一化到0-100
        total_score = np.clip(total_score, 0, 100)

        if verbose:
            details = {
                'color_richness_score': round(color_richness_score, 2),
                'hue_entropy_score': round(hue_score, 2),
                'saturation_score': round(saturation_score, 2),
                'brightness_score': round(brightness_score, 2),
                'brightness_value': round(v_mean, 3),
                'contrast_score': round(contrast_score, 2),
                'contrast_std': round(v_std, 3),
                'dynamic_range': round(dynamic_range, 3),
                'dark_ratio': round(dark_ratio, 3),
                'bright_ratio': round(bright_ratio, 3),
                'total_score': round(total_score, 2)
            }
            return total_score, details

        return total_score


    def batch_image_quality_scores(self, image_paths):
        """
        批量处理图片并返回评分

        Parameters:
        -----------
        image_paths : list
            图片路径列表

        Returns:
        --------
        scores : dict
            图片路径到评分的映射
        """
        scores = {}
        for path in image_paths:
            try:
                score = self.image_quality_score(path)
                scores[path] = score
            except Exception as e:
                scores[path] = f"Error: {str(e)}"
        return scores


# 使用示例
if __name__ == "__main__":
    # 单张图片测试
    test_image = "5250024851118516-7.jpg"  # 替换为您的图片路径
    model = Color_richness()
    try:
        # 基础评分
        score = model.image_quality_score(test_image)
        print(f"图片综合质量评分: {score:.2f}/100")

        # 详细评分
        score, details = model.image_quality_score(test_image, verbose=True)
        print("\n=== 详细评分报告 ===")
        print(f"色彩丰富度: {details['color_richness_score']}/30")
        print(f"  - 色调熵值: {details['hue_entropy_score']}/15")
        print(f"  - 饱和度: {details['saturation_score']}/15")
        print(f"亮度评分: {details['brightness_score']}/30")
        print(f"  - 平均亮度: {details['brightness_value']}")
        print(f"  - 暗部比例: {details['dark_ratio'] * 100:.1f}%")
        print(f"  - 亮部比例: {details['bright_ratio'] * 100:.1f}%")
        print(f"对比度评分: {details['contrast_score']}/40")
        print(f"  - 标准差: {details['contrast_std']}")
        print(f"  - 动态范围: {details['dynamic_range']}")
        print(f"\n总分: {details['total_score']}/100")

        # 根据分数给出质量评级
        if details['total_score'] >= 80:
            print("质量评级: 优质 (适合用于高质量宣传)")
        elif details['total_score'] >= 60:
            print("质量评级: 良好")
        elif details['total_score'] >= 40:
            print("质量评级: 中等")
        else:
            print("质量评级: 较差")

    except Exception as e:
        print(f"处理出错: {e}")