# -*- coding: utf-8 -*-
import os

os.environ['HF_HUB_DISABLE_SYMLINKS_WARNING'] = '1'

import torch
import torch.nn as nn
from transformers import BertTokenizer, BertModel, BertPreTrainedModel


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


class sentiment_analysis():
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


#
# LABEL_MAP = {
#     0: "中性",
#     1: "负面-恐慌/恶意唱空（高风险）",
#     2: "负面-理性担忧（低风险）",
#     3: "正面-理性看好（低风险）",
#     4: "正面-过度狂热（高风险）"
# }
#
# RISK_MAP = {0: "无风险", 1: "高风险", 2: "低风险", 3: "低风险", 4: "高风险"}
#
#
# def load_model(model_path, model_name='hfl/chinese-roberta-wwm-ext', device='cpu'):
#     tokenizer = BertTokenizer.from_pretrained(model_name)
#     model = FinBERT5Class(model_name=model_name)
#     # ✅ 修复：添加 weights_only=False 兼容 PyTorch 2.6
#     checkpoint = torch.load(model_path, map_location=device, weights_only=False)
#     model.load_state_dict(checkpoint['model_state_dict'])
#     model.to(device)
#     model.eval()
#     label_map = checkpoint.get('label_map', LABEL_MAP)
#     return model, tokenizer, label_map
#
#
# def predict(text, model, tokenizer, label_map, device='cpu'):
#     encoding = tokenizer(text, truncation=True, padding='max_length', max_length=128,
#                          return_tensors='pt', return_token_type_ids=True)
#     input_ids = encoding['input_ids'].to(device)
#     attention_mask = encoding['attention_mask'].to(device)
#     token_type_ids = encoding['token_type_ids'].to(device)
#     with torch.no_grad():
#         outputs = model(input_ids, attention_mask, token_type_ids)
#         logits = outputs['logits']
#         probs = torch.softmax(logits, dim=1)
#         pred = torch.argmax(probs, dim=1).item()
#         confidence = probs[0][pred].item()
#     return {
#         'text': text,
#         'sentiment': label_map[pred],
#         'label_id': pred,
#         'risk_level': RISK_MAP[pred],
#         'confidence': round(confidence, 4)
#     }


if __name__ == "__main__":
    model = sentiment_analysis()
    text = "3.2日大饼的思路仍然保持不变，等下行至839附近设置保本，看782附近"
    result = model.predict(text)
    print("\n" + "=" * 50)
    print(f"文本：{result['text']}")
    print(f"情感：{result['sentiment']}")
    print(f"风险等级：{result['risk_level']}")
    print(f"置信度：{result['confidence']}")
    print("=" * 50)

    # MODEL_PATH = 'finbert_5class_best.pth'
    # DEVICE = 'cuda' if torch.cuda.is_available() else 'cpu'
    # model, tokenizer, label_map = load_model('finbert_5class_best.pth', device='cuda' if torch.cuda.is_available() else 'cpu')
    # print("✓ 模型加载成功\n")
    # text = "3.2日大饼的思路仍然保持不变，等下行至839附近设置保本，看782附近"
    # result = predict(text, model, tokenizer, label_map, DEVICE)
    # print("\n" + "=" * 50)
    # print(f"文本：{result['text']}")
    # print(f"情感：{result['sentiment']}")
    # print(f"风险等级：{result['risk_level']}")
    # print(f"置信度：{result['confidence']}")
    # print("=" * 50)