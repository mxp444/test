import os
import json
import time
from wechat_ocr.ocr_manager import OcrManager, OCR_MAX_TASK_ID


class OCR():
    def __init__(self):
        self.wechat_ocr_dir = r"C:\Users\R9000P\AppData\Roaming\Tencent\WeChat\XPlugin\Plugins\WeChatOCR\\7079\extracted\WeChatOCR.exe"
        self.wechat_dir = r"C:\Program Files\Tencent\Weixin\\4.1.7.59"
        self.output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "json")
        os.makedirs(self.output_dir, exist_ok=True)

        self.ocr_manager = OcrManager(self.wechat_dir)
        # 设置WeChatOcr目录
        self.ocr_manager.SetExePath(self.wechat_ocr_dir)
        # 设置微信所在路径
        self.ocr_manager.SetUsrLibDir(self.wechat_dir)
        # 设置ocr识别结果的回调函数
        self.ocr_manager.SetOcrResultCallback(self.ocr_result_callback)
        # 启动ocr服务
        self.ocr_manager.StartWeChatOCR()

    def ocr_result_callback(self, img_path: str, results: dict):
        result_file = os.path.join(self.output_dir, os.path.basename(img_path) + ".json")
        print(f"识别成功，img_path: {img_path}, result_file: {result_file}")
        with open(result_file, 'w', encoding='utf-8') as f:
            f.write(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":

    model = OCR()
    # 开始识别图片

    model.ocr_manager.DoOCRTask(r"pics/cd11b4851a0b415cd1a7f7c98560708f.jpg")
    model.ocr_manager.DoOCRTask(r"pics\490f705bd73faaa6711001ea4ae5de15.jpeg")
    time.sleep(1)
    while model.ocr_manager.m_task_id.qsize() != OCR_MAX_TASK_ID:
        pass
    # 识别输出结果
    model.ocr_manager.KillWeChatOCR()

