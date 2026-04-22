import cv2
import numpy as np


def _read_image(image_path):
    data = np.fromfile(image_path, dtype=np.uint8)
    if data.size == 0:
        return None
    return cv2.imdecode(data, cv2.IMREAD_COLOR)


class Ambiguity:
    def predict(self, image_path):
        processed_image = self.preprocess_image(image_path)
        return self.calculate_blur_score(processed_image)

    def preprocess_image(self, image_path, target_size=(300, 300), blur_kernel_size=5):
        image = _read_image(image_path)
        if image is None:
            raise ValueError(f"无法读取图片: {image_path}")

        resized_image = cv2.resize(image, target_size)
        gray = cv2.cvtColor(resized_image, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (blur_kernel_size, blur_kernel_size), 0)
        return blurred

    def calculate_blur_score(self, image):
        laplacian = cv2.Laplacian(image, cv2.CV_64F)
        laplacian = np.uint8(np.absolute(laplacian))
        edge_strength = np.mean(laplacian)
        return edge_strength


if __name__ == "__main__":
    image_path = "pics/42df34ee5174b3088d54020817c50abd.jpeg"
    model = Ambiguity()
    blur_score = model.predict(image_path)
    print("图像模糊程度:", blur_score)
