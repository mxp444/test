# -*- coding: utf-8 -*-
import os

os.environ['HF_HUB_DISABLE_SYMLINKS_WARNING'] = '1'

import torch
import torch.nn as nn
from transformers import BertTokenizer, BertModel, BertPreTrainedModel

# 0: "中性",
# 1: "负面-恐慌/恶意唱空（高风险）",
# 2: "负面-理性担忧（低风险）",
# 3: "正面-理性看好（低风险）",
# 4: "正面-过度狂热（高风险）"

class FinBERT5Class(BertPreTrainedModel):
    def __init__(self, num_classes=5, model_name='hfl/chinese-roberta-wwm-ext'):
        super().__init__(BertPreTrainedModel.config_class.from_pretrained(model_name))
        self.bert = BertModel.from_pretrained(model_name)
        self.hidden_size = self.bert.config.hidden_size
        self.config.num_labels = num_classes
        self.classifier = nn.Linear(self.hidden_size, num_classes)

    def forward(self, input_ids, attention_mask, token_type_ids=None):
        outputs = self.bert(input_ids=input_ids, attention_mask=attention_mask, token_type_ids=token_type_ids)
        pooled_output = outputs.pooler_output
        logits = self.classifier(pooled_output)
        return {'logits': logits}


class Sentiment_analysis():
    def __init__(self):
        self.LABEL_MAP = {
            0: "中性",
            1: "负面-恐慌/恶意唱空（高风险）",
            2: "负面-理性担忧（低风险）",
            3: "正面-理性看好（低风险）",
            4: "正面-过度狂热（高风险）"
        }
        self.RISK_MAP = {0: "无风险", 1: "高风险", 2: "低风险", 3: "低风险", 4: "高风险"}
        self.model_name = 'hfl/chinese-roberta-wwm-ext'
        self.MODEL_PATH = 'finbert_5class_best.pth'
        self.DEVICE = 'cuda' if torch.cuda.is_available() else 'cpu'
        self.tokenizer = BertTokenizer.from_pretrained(self.model_name)
        self.model = FinBERT5Class(model_name=self.model_name)
        # ✅ 修复：添加 weights_only=False 兼容 PyTorch 2.6
        self.checkpoint = torch.load(self.MODEL_PATH, map_location=self.DEVICE, weights_only=False)
        self.model.load_state_dict(self.checkpoint['model_state_dict'])
        self.model.to(self.DEVICE)
        self.model.eval()
        self.label_map = self.checkpoint.get('label_map', self.LABEL_MAP)

    def predict(self, text):
        encoding = self.tokenizer(text, truncation=True, padding='max_length', max_length=128,
                             return_tensors='pt', return_token_type_ids=True)
        input_ids = encoding['input_ids'].to(self.DEVICE)
        attention_mask = encoding['attention_mask'].to(self.DEVICE)
        token_type_ids = encoding['token_type_ids'].to(self.DEVICE)
        with torch.no_grad():
            outputs = self.model(input_ids, attention_mask, token_type_ids)
            logits = outputs['logits']
            probs = torch.softmax(logits, dim=1)
            pred = torch.argmax(probs, dim=1).item()
            confidence = probs[0][pred].item()
        return {
            'text': text,
            'sentiment': self.label_map[pred],
            'label_id': pred,
            'risk_level': self.RISK_MAP[pred],
            'confidence': round(confidence, 4)
        }


if __name__ == "__main__":
    model = Sentiment_analysis()
    text = "3.2日大饼的思路仍然保持不变，等下行至839附近设置保本，看782附近"
    result = model.predict(text)
    print("\n" + "=" * 50)
    print(f"文本：{result['text']}")
    print(f"情感：{result['sentiment']}")
    print(f"风险等级：{result['risk_level']}")
    print(f"置信度：{result['confidence']}")
    print("=" * 50)
