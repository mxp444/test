import cv2
import numpy as np


def _read_image(image_path):
    data = np.fromfile(image_path, dtype=np.uint8)
    if data.size == 0:
        return None
    return cv2.imdecode(data, cv2.IMREAD_COLOR)


class Color_richness:
    def image_quality_score(self, image_path, verbose=False):
        img = _read_image(image_path)
        if img is None:
            raise ValueError(f"无法读取图片: {image_path}")

        img_hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        h, s, v = cv2.split(img_hsv)

        h_hist = cv2.calcHist([h], [0], None, [180], [0, 180])
        h_hist_normalized = h_hist / max(h_hist.sum(), 1)
        h_entropy = -np.sum(h_hist_normalized * np.log2(h_hist_normalized + 1e-10))
        hue_score = min(15, float(h_entropy) * 2)

        s_mean = np.mean(s) / 255.0
        s_std = np.std(s) / 255.0
        if 0.3 <= s_mean <= 0.7:
            saturation_mean_score = 7.5
        else:
            deviation = min(abs(s_mean - 0.3), abs(s_mean - 0.7))
            saturation_mean_score = max(0, 7.5 * (1 - deviation * 2))
        saturation_std_score = min(7.5, s_std * 15)
        saturation_score = saturation_mean_score + saturation_std_score
        color_richness_score = hue_score + saturation_score

        v_mean = np.mean(v) / 255.0
        if 0.4 <= v_mean <= 0.7:
            brightness_score = 20
        elif v_mean < 0.4:
            brightness_score = 20 * (v_mean / 0.4)
        else:
            brightness_score = 20 * ((1 - v_mean) / 0.3)

        v_hist = cv2.calcHist([v], [0], None, [256], [0, 256])
        v_hist_normalized = v_hist / max(v_hist.sum(), 1)
        dark_ratio = float(np.sum(v_hist_normalized[:51]))
        bright_ratio = float(np.sum(v_hist_normalized[200:]))
        if dark_ratio > 0.3:
            brightness_score -= 5 * (dark_ratio - 0.3) * 2
        if bright_ratio > 0.3:
            brightness_score -= 5 * (bright_ratio - 0.3) * 2
        brightness_score = float(np.clip(brightness_score, 0, 30))

        v_std = np.std(v) / 255.0
        contrast_std_score = min(20, v_std * 40)
        v_flat = v.flatten()
        p5 = np.percentile(v_flat, 5) / 255.0
        p95 = np.percentile(v_flat, 95) / 255.0
        dynamic_range = p95 - p5
        if 0.4 <= dynamic_range <= 0.8:
            dynamic_range_score = 15
        else:
            dynamic_range_score = 15 * (1 - abs(dynamic_range - 0.6) / 0.6)
        rms_contrast = (v_std / v_mean) if v_mean > 0 else 0
        rms_score = min(5, rms_contrast * 10)
        contrast_score = float(np.clip(contrast_std_score + dynamic_range_score + rms_score, 0, 40))

        total_score = float(np.clip(color_richness_score + brightness_score + contrast_score, 0, 100))

        if verbose:
            details = {
                "color_richness_score": round(color_richness_score, 2),
                "hue_entropy_score": round(hue_score, 2),
                "saturation_score": round(saturation_score, 2),
                "brightness_score": round(brightness_score, 2),
                "brightness_value": round(v_mean, 3),
                "contrast_score": round(contrast_score, 2),
                "contrast_std": round(v_std, 3),
                "dynamic_range": round(dynamic_range, 3),
                "dark_ratio": round(dark_ratio, 3),
                "bright_ratio": round(bright_ratio, 3),
                "total_score": round(total_score, 2),
            }
            return total_score, details

        return total_score

    def batch_image_quality_scores(self, image_paths):
        scores = {}
        for path in image_paths:
            try:
                scores[path] = self.image_quality_score(path)
            except Exception as exc:
                scores[path] = f"Error: {exc}"
        return scores


if __name__ == "__main__":
    test_image = r"C:\Users\R9000P\Desktop\毕设\整合\pics\490f705bd73faaa6711001ea4ae5de15.jpeg"
    model = Color_richness()
    score, details = model.image_quality_score(test_image, verbose=True)
    print(f"图像综合质量评分: {score:.2f}/100")
    print(details)
