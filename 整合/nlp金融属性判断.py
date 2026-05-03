"""
测试模型性能
标签种类有
0：非金融舆情类但胜似金融舆情（招商、合伙人、返利、层级分红）
1：完全非金融舆情类（生活、日常、兴趣）
2：金融诈骗话术（高收益、保本兜底、拉下线、庞氏）
3：理财经理产品推销（正规理财、基金、存款、信托）
4：客户视角理财分享（个人理财经历、收益、产品）
5：金融避雷踩坑吐槽（被骗、踩坑、提醒）
6：A 股股价走势分析（大盘、板块、个股、行情）
7：金融政策监管动态解读（央行、监管局、政策）
8：基金定投相关讨论（定投技巧、误区、方法）
9：保险产品测评讨论（保险选购、险种、建议）
10：期货贵金属投资讨论（黄金、原油、期货、风险）
11：数字货币相关舆情（比特币、监管、虚拟币）
"""
import torch
import numpy as np
import joblib
import os
from pathlib import Path

os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

from transformers import BertTokenizer, BertForSequenceClassification



class Financial_attribute():
    def __init__(self, model_dir="./my_finance_bert_wwm"):
        model_path = Path(model_dir)
        if not model_path.is_absolute():
            model_path = Path(__file__).resolve().parent / model_path
        model_path = model_path.resolve()
        if not model_path.exists():
            raise FileNotFoundError(f"金融属性模型目录不存在: {model_path}")

        self.tokenizer = BertTokenizer.from_pretrained(str(model_path), local_files_only=True)
        self.model = BertForSequenceClassification.from_pretrained(str(model_path), local_files_only=True)
        self.label_encoder = joblib.load(model_path / "label_encoder.pkl")
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model.to(self.device)
        self.model.eval()

    def predict_multilabel_topk(self, text, k=4):
        """
        返回概率最高的前 k 个标签及其概率
        """
        inputs = self.tokenizer(text, padding="max_length", truncation=True, max_length=512, return_tensors="pt")
        inputs = {k: v.to(self.device) for k, v in inputs.items()}

        with torch.no_grad():
            outputs = self.model(**inputs)
            logits = outputs.logits
            probs = torch.softmax(logits, dim=-1).cpu().numpy()[0]

        topk_indices = np.argsort(probs)[::-1][:k]
        labels = self.label_encoder.inverse_transform(topk_indices)
        probs_topk = probs[topk_indices]

        result = [(labels[i], probs_topk[i]) for i in range(k)]
        return result


if __name__ == "__main__":

    print("正在加载模型...")
    model = Financial_attribute()
    print(f"模型加载成功")

    text = "最近有个项目宣称保本高收益，年化20%，发展下线还有返利，是不是骗局？"

    result = model.predict_multilabel_topk(text)

    for i, j in result:
        print(f"label({i}), confidence:{j:.2f}")
