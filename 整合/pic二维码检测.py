import base64
import io

import cv2
import numpy as np
from PIL import Image


def _read_image(image_path):
    data = np.fromfile(image_path, dtype=np.uint8)
    if data.size == 0:
        return None
    return cv2.imdecode(data, cv2.IMREAD_COLOR)


class QR_code_detector:
    def __init__(self):
        self.qr_detector = cv2.QRCodeDetector()

    def detect_and_decode(self, image_path=None, image_data=None):
        try:
            if image_path:
                img = _read_image(image_path)
            elif image_data:
                nparr = np.frombuffer(image_data, np.uint8)
                img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            else:
                return {"error": "没有提供图像数据"}

            if img is None:
                return {"error": f"无法读取图像: {image_path}"}

            original_height, original_width = img.shape[:2]
            gray_img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            gauss_img = cv2.GaussianBlur(gray_img, (9, 9), 0)
            median_img = cv2.medianBlur(gauss_img, 5)
            _, thr = cv2.threshold(median_img, 50, 255, cv2.THRESH_BINARY)

            data, bbox, _ = self.qr_detector.detectAndDecode(img)

            result = {
                "success": True,
                "original_size": f"{original_width}x{original_height}",
                "qr_data": data if data else None,
                "processing_steps": {
                    "original": self._image_to_base64(img),
                    "grayscale": self._image_to_base64(cv2.cvtColor(gray_img, cv2.COLOR_GRAY2BGR)),
                    "gaussian_blur": self._image_to_base64(cv2.cvtColor(gauss_img, cv2.COLOR_GRAY2BGR)),
                    "median_blur": self._image_to_base64(cv2.cvtColor(median_img, cv2.COLOR_GRAY2BGR)),
                    "binary": self._image_to_base64(cv2.cvtColor(thr, cv2.COLOR_GRAY2BGR)),
                },
            }

            if bbox is not None and len(bbox) > 0:
                bbox_array = np.array(bbox, dtype=np.int32)
                img_with_bbox = img.copy()
                cv2.polylines(img_with_bbox, [bbox_array], True, (0, 255, 0), 3)
                result["processing_steps"]["detection"] = self._image_to_base64(img_with_bbox)
                result["qr_detected"] = True
                result["qr_bbox"] = bbox_array.tolist()
            else:
                result["processing_steps"]["detection"] = self._image_to_base64(img)
                result["qr_detected"] = False
                result["qr_bbox"] = None

            return result
        except Exception as exc:
            return {"error": f"处理二维码时出错: {exc}"}

    def _image_to_base64(self, image):
        try:
            if len(image.shape) == 3:
                image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            else:
                image_rgb = image

            pil_image = Image.fromarray(image_rgb)
            buffer = io.BytesIO()
            pil_image.save(buffer, format="PNG")
            buffer.seek(0)
            img_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
            return f"data:image/png;base64,{img_base64}"
        except Exception:
            return ""


if __name__ == "__main__":
    detector = QR_code_detector()
    result = detector.detect_and_decode("pics/f97c511ba970ba119590ad18aec2e0b5.jpeg")
    print("是否有二维码", result.get("qr_detected"), "二维码像素位置", result.get("qr_bbox"))
