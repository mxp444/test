import os
import json
import time
from wechat_ocr.ocr_manager import OcrManager, OCR_MAX_TASK_ID

wechat_ocr_dir = r"C:\Users\R9000P\AppData\Roaming\Tencent\WeChat\XPlugin\Plugins\WeChatOCR\\7079\extracted\WeChatOCR.exe"
wechat_dir = r"C:\Program Files\Tencent\Weixin\\4.1.7.59"


def ocr_result_callback(img_path: str, results: dict):
    result_file = "./json/" + os.path.basename(img_path) + ".json"
    print(f"识别成功，img_path: {img_path}, result_file: {result_file}")
    with open(result_file, 'w', encoding='utf-8') as f:
        f.write(json.dumps(results, ensure_ascii=False, indent=2))


def main():
    ocr_manager = OcrManager(wechat_dir)
    # 设置WeChatOcr目录
    ocr_manager.SetExePath(wechat_ocr_dir)
    # 设置微信所在路径
    ocr_manager.SetUsrLibDir(wechat_dir)
    # 设置ocr识别结果的回调函数
    ocr_manager.SetOcrResultCallback(ocr_result_callback)
    # 启动ocr服务
    ocr_manager.StartWeChatOCR()
    # 开始识别图片
    ocr_manager.DoOCRTask(r"pics/42df34ee5174b3088d54020817c50abd.jpeg")
    ocr_manager.DoOCRTask(r"pics/cd11b4851a0b415cd1a7f7c98560708f.jpg")
    ocr_manager.DoOCRTask(r"pics\490f705bd73faaa6711001ea4ae5de15.jpeg")
    time.sleep(1)
    while ocr_manager.m_task_id.qsize() != OCR_MAX_TASK_ID:
        pass
    # 识别输出结果
    ocr_manager.KillWeChatOCR()


if __name__ == "__main__":
    main()

