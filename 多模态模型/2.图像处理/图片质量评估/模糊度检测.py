import cv2
import numpy as np

class ambiguity():

    def predict(self, image_path):
        processed_image = self.preprocess_image(image_path)

        # 计算图像模糊程度
        blur_score = self.calculate_blur_score(processed_image)
        return blur_score

    def preprocess_image(self, image_path, target_size=(300, 300), blur_kernel_size=5):
        # 读取图像
        image = cv2.imread(image_path)

        # 将图像缩放到目标大小
        resized_image = cv2.resize(image, target_size)

        # 将图像转换为灰度图
        gray = cv2.cvtColor(resized_image, cv2.COLOR_BGR2GRAY)

        # 使用高斯模糊去除噪点
        blurred = cv2.GaussianBlur(gray, (blur_kernel_size, blur_kernel_size), 0)

        return blurred

    def calculate_blur_score(self, image):
        # 使用拉普拉斯算子计算图像的边缘
        laplacian = cv2.Laplacian(image, cv2.CV_64F)

        # 取绝对值，并转换为8位图像
        laplacian = np.uint8(np.absolute(laplacian))

        # 计算边缘强度
        edge_strength = np.mean(laplacian)

        return edge_strength



if __name__ == "__main__":
    # 输入图像路径
    image_path = "5250024851118516-7.jpg"
    model = ambiguity()
    blur_score = model.predict(image_path)
    print("图像模糊程度：", blur_score)

