"""
测试模型性能
"""
import torch
import numpy as np
import joblib
import os
from transformers import BertTokenizer, BertForSequenceClassification



class financial_attribute():
    def __init__(self, model_dir="./my_finance_bert_wwm"):
        self.tokenizer = BertTokenizer.from_pretrained(model_dir)
        self.model = BertForSequenceClassification.from_pretrained(model_dir)
        self.label_encoder = joblib.load(os.path.join(model_dir, "label_encoder.pkl"))
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

        # 取前 k 个最大概率的索引
        topk_indices = np.argsort(probs)[::-1][:k]
        labels = self.label_encoder.inverse_transform(topk_indices)
        probs_topk = probs[topk_indices]

        result = [(labels[i], probs_topk[i]) for i in range(k)]
        return result










# def load_model_and_encoder(model_dir):
#     """
#     加载模型、分词器和标签编码器
#     """
#     tokenizer = BertTokenizer.from_pretrained(model_dir)
#     model = BertForSequenceClassification.from_pretrained(model_dir)
#     label_encoder = joblib.load(os.path.join(model_dir, "label_encoder.pkl"))
#     device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
#     model.to(device)
#     model.eval()
#     return model, tokenizer, label_encoder, device
#
# def predict_multilabel_topk(text, model, tokenizer, label_encoder, device, k=3):
#     """
#     返回概率最高的前 k 个标签及其概率
#     """
#     inputs = tokenizer(text, padding="max_length", truncation=True, max_length=512, return_tensors="pt")
#     inputs = {k: v.to(device) for k, v in inputs.items()}
#
#     with torch.no_grad():
#         outputs = model(**inputs)
#         logits = outputs.logits
#         probs = torch.softmax(logits, dim=-1).cpu().numpy()[0]
#
#     # 取前 k 个最大概率的索引
#     topk_indices = np.argsort(probs)[::-1][:k]
#     labels = label_encoder.inverse_transform(topk_indices)
#     probs_topk = probs[topk_indices]
#
#     result = [(labels[i], probs_topk[i]) for i in range(k)]
#     return result

if __name__ == "__main__":
    # 模型保存路径（请根据实际情况修改）
    print("正在加载模型...")
    model = financial_attribute()
    print(f"模型加载成功")

    # 示例文本
    text = "最近有个项目宣称保本高收益，年化20%，发展下线还有返利，是不是骗局？"

    # "今天上证指数涨了1.5%，创业板指大涨2%，科技股表现强势。",
    # "最近在理财群里看到个项目，宣称保本高收益，拉人头还有三级返利，这明显是庞氏骗局，我赶紧退群了；不过群里有人聊到最近A股，说创业板指反弹，新能源板块又起来了，我倒是挺关注行情；另外还有个群友在纠结给孩子买重疾险，对比了好几个产品，不知道该选消费型还是返还型。"

    result = model.predict_multilabel_topk(text)

    for i, j in result:
        print(f"label({i}), confidence:{j:.2f}")