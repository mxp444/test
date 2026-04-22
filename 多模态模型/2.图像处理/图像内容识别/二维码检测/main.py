import cv2
import numpy as np
import base64
import io
from PIL import Image


class QRCodeDetector:
    def __init__(self):
        self.qr_detector = cv2.QRCodeDetector()

    def detect_and_decode(self, image_path=None, image_data=None):
        """
        检测并解码二维码
        :param image_path: 图片路径
        :param image_data: 图片数据（bytes）
        :return: 检测结果字典
        """
        try:
            # 读取图像
            if image_path:
                img = cv2.imread(image_path)
            elif image_data:
                nparr = np.frombuffer(image_data, np.uint8)
                img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            else:
                return {"error": "没有提供图像数据"}

            if img is None:
                return {"error": "无法读取图像"}

            # 获取原始图像信息
            original_height, original_width = img.shape[:2]

            # 1. 灰度化处理
            gray_img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

            # 2. 高斯滤波降噪
            gauss_img = cv2.GaussianBlur(gray_img, (9, 9), 0)

            # 3. 中值滤波进一步降噪
            median_img = cv2.medianBlur(gauss_img, 5)

            # 4. 图像二值化
            ret, thr = cv2.threshold(median_img, 50, 255, cv2.THRESH_BINARY)

            # 5. 使用OpenCV内置二维码检测器
            data, bbox, rectified_image = self.qr_detector.detectAndDecode(img)

            result = {
                "success": True,
                "original_size": f"{original_width}x{original_height}",
                "qr_data": data if data else "未检测到二维码内容",
                "processing_steps": {}
            }

            # 将处理步骤的图像转换为base64
            result["processing_steps"]["original"] = self._image_to_base64(img)
            result["processing_steps"]["grayscale"] = self._image_to_base64(
                cv2.cvtColor(gray_img, cv2.COLOR_GRAY2BGR)
            )
            result["processing_steps"]["gaussian_blur"] = self._image_to_base64(
                cv2.cvtColor(gauss_img, cv2.COLOR_GRAY2BGR)
            )
            result["processing_steps"]["median_blur"] = self._image_to_base64(
                cv2.cvtColor(median_img, cv2.COLOR_GRAY2BGR)
            )
            result["processing_steps"]["binary"] = self._image_to_base64(
                cv2.cvtColor(thr, cv2.COLOR_GRAY2BGR)
            )

            # 如果有检测到二维码，绘制边界框
            if bbox is not None and len(bbox) > 0:
                # 绘制二维码边界框
                img_with_bbox = img.copy()

                # 正确处理bbox的结构
                # bbox通常是一个包含4个点的数组，每个点是[x, y]
                try:
                    # 将bbox转换为整数类型
                    bbox_array = np.array(bbox, dtype=np.int32)

                    # 绘制边界框
                    cv2.polylines(img_with_bbox, [bbox_array], True, (0, 255, 0), 3)

                    # 在图像上显示检测到的内容
                    if data:
                        # 计算左上角坐标（取所有点中最小的x和y）
                        x = int(np.min(bbox_array[:, 0]))
                        y = int(np.min(bbox_array[:, 1]))

                        # 确保坐标在图像范围内
                        y = max(10, y)  # 确保文字不会超出图像顶部

                        # 添加文字背景（可选，提高可读性）
                        text = f"QR: {data[:20]}..."
                        (text_width, text_height), baseline = cv2.getTextSize(
                            text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)

                        # 绘制文字背景
                        cv2.rectangle(img_with_bbox,
                                      (x, y - text_height - 10),
                                      (x + text_width, y - 5),
                                      (0, 255, 0), -1)

                        # 绘制白色文字
                        cv2.putText(img_with_bbox, text,
                                    (x, y - 10),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 2)

                    result["processing_steps"]["detection"] = self._image_to_base64(img_with_bbox)
                    result["qr_detected"] = True
                    result["qr_bbox"] = bbox_array.tolist()

                except Exception as e:
                    print(f"绘制边界框时出错: {e}")
                    result["processing_steps"]["detection"] = self._image_to_base64(img)
                    result["qr_detected"] = False
            else:
                result["processing_steps"]["detection"] = self._image_to_base64(img)
                result["qr_detected"] = False
                result["qr_bbox"] = None  # 或 []，确保键存在

            return result

        except Exception as e:
            import traceback
            print(f"详细错误信息: {traceback.format_exc()}")
            return {"error": f"处理过程中出现错误: {str(e)}"}

    def _image_to_base64(self, image):
        """将OpenCV图像转换为base64字符串"""
        try:
            # 将BGR图像转换为RGB
            if len(image.shape) == 3:
                image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            else:
                image_rgb = image

            # 转换为PIL图像
            pil_image = Image.fromarray(image_rgb)

            # 创建字节缓冲区
            buffer = io.BytesIO()
            pil_image.save(buffer, format='PNG')
            buffer.seek(0)

            # 转换为base64
            img_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
            return f"data:image/png;base64,{img_base64}"

        except Exception as e:
            print(f"图像转换错误：{e}")
            return ""

    def _image_to_base64(self, image):
        """将OpenCV图像转换为base64字符串"""
        try:
            # 将BGR图像转换为RGB
            if len(image.shape) == 3:
                image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            else:
                image_rgb = image

            # 转换为PIL图像
            pil_image = Image.fromarray(image_rgb)

            # 创建字节缓冲区
            buffer = io.BytesIO()
            pil_image.save(buffer, format='PNG')
            buffer.seek(0)

            # 转换为base64
            img_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
            return f"data:image/png;base64,{img_base64}"

        except Exception as e:
            print(f"图像转换错误：{e}")
            return ""

if __name__ == "__main__":
    detector = QRCodeDetector()
    result = detector.detect_and_decode("42df34ee5174b3088d54020817c50abd.jpeg")
    print(result["qr_detected"], result["qr_bbox"])