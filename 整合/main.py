import time
# -*- coding: utf-8 -*-
from nlp金融属性判断 import Financial_attribute
from nlp风险要素识别 import Risk_factor
from nlp情感分析 import Sentiment_analysis
from nlp煽动性评估 import Incitement_evaluator
from picOCR文字识别 import OCR
from pic二维码检测 import QR_code_detector
from pic模糊度检测 import Ambiguity
from pic色彩丰富程度 import Color_richness
from pic设计感 import Design_sense



class Financial_public_opinion_risk_detection():
    def __init__(self):
        self.Financial_attribute = Financial_attribute()
        self.Risk_factor = Risk_factor()
        self.Sentiment_analysis = Sentiment_analysis()
        self.Incitement_evaluator = Incitement_evaluator()
        self.OCR = OCR()
        self.QR_code_detector = QR_code_detector()
        self.Ambiguity = Ambiguity()
        self.Color_richness = Color_richness()
        self.Design_sense = Design_sense()

    def nlp(self, text):
        result1 = self.Financial_attribute.predict_multilabel_topk(text)
        for i, j in result1:
            print(f"金融属性label({i}), confidence:{j:.2f}")

        result2, summary = self.Risk_factor.analyze_text(text)
        for k, v in summary.items():
            if v > 0 or "总风险" in k:
                print(f"{k}: {v}")
        print("\n--- 详细命中词 ---")
        for cat, words in result2.items():
            if words and cat != "未分类":
                print(f"\n[{cat}]")
                for w in words:
                    print(f"  - {w['word']} ({w['score']:.2f})")

        result3 = self.Sentiment_analysis.predict(text)
        print(f"文本：{result3['text']}")
        print(f"情感：{result3['sentiment']}")
        print(f"风险等级：{result3['risk_level']}")
        print(f"置信度：{result3['confidence']}")

        result4 = self.Incitement_evaluator.evaluate(text)
        print(f"总分: {result4['total_score']}/100")
        print(f"风险等级: {result4['risk_level']}")
        print(f"风险描述: {result4['risk_description']}")
        print("\n各维度得分:")
        print(f"  - 语气强烈程度: {result4['dimensions']['tone']['score']}/40 "
              f"({result4['dimensions']['tone']['percentage']}%)")
        print(f"  - 稀缺性暗示: {result4['dimensions']['scarcity']['score']}/30 "
              f"({result4['dimensions']['scarcity']['percentage']}%)")
        print(f"  - 从众压力: {result4['dimensions']['herd']['score']}/30 "
              f"({result4['dimensions']['herd']['percentage']}%)")
        print(f"\n建议: {result4['recommendation']}")
        if result4['total_score'] >= 60:  # 高风险才打印详细
            print("\n【详细检测结果】")
            if result4['dimensions']['tone']['details']['extreme_words_found']:
                print(f"检测到的极端词: {result4['dimensions']['tone']['details']['extreme_words_found']}")
            if result4['dimensions']['scarcity']['details']['matched_patterns']:
                print(f"检测到的稀缺性模式: {result4['dimensions']['scarcity']['details']['matched_patterns']}")
            if result4['dimensions']['herd']['details']['matched_patterns']:
                print(f"检测到的从众压力模式: {result4['dimensions']['herd']['details']['matched_patterns']}")


    def cv(self, pic):
        self.OCR.ocr_manager.DoOCRTask(pic)
        time.sleep(1)

        result = self.QR_code_detector.detect_and_decode(pic)
        print("二维码检测", result["qr_detected"], result["qr_bbox"])

        blur_score = self.Ambiguity.predict(pic)
        print("图像模糊程度：", blur_score)

        score = self.Color_richness.image_quality_score(pic)
        print(f"图片综合质量评分: {score:.2f}/100")
        # 详细评分
        score, details = self.Color_richness.image_quality_score(pic, verbose=True)
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

        mean, std = self.Design_sense.predict(pic)
        print("NIMA Score : %0.3f +- (%0.3f)" % (mean, std))


if __name__ == '__main__':
    model = Financial_public_opinion_risk_detection()
    text = """美股指数基金主要投资于指数成份股，这些成份股，
    通常会覆盖多个行业和板块，所以能分散风险，长期收益较稳定，
    而且操作简单方便，对个人投资者来说比较友好。我们在选择指数
    基金的时候，1、首先你需要明确自己的投资目标，包括你的投资期
    限，预期收益，风险承受能力。你是保守保本型，稳健固收型，还是
    权益增长型。2、选择合适的指数，如标普、纳指、国债等指数。例如
    ，你希望投资大盘股，可以选择标普500这样的指数。如果你对科技、
    人工智能，AI行业感兴趣，可以选择纳指100，这样的指数。3、指数
    基金费用，美股指数基金，申赎零费用，管理费也比较低，费用的高低
    会直接影响到你的投资收益。因此，我们尽量选择零成本交易平台。4、
    查看指数基金的历史业绩，虽然历史业绩不能保证未来表现，但它过往
    表现，可以为你提供一些参考信息。可以查看指数基金过去十年、三十
    年、五十年的年化收益率，波动率等一些指标，评估值不值得投资。#香
    港理财财富管理##保险基金#"""
    pic = "pics/f97c511ba970ba119590ad18aec2e0b5.jpeg"
    model.nlp(text)
    model.cv(pic)
