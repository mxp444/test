# -*- coding: utf-8 -*-
import os
from pathlib import Path

os.environ['HF_HUB_DISABLE_SYMLINKS_WARNING'] = '1'
os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

import torch
import torch.nn as nn
from transformers import BertConfig, BertTokenizer, BertModel, BertPreTrainedModel

# 0: "中性",
# 1: "负面-恐慌/恶意唱空（高风险）",
# 2: "负面-理性担忧（低风险）",
# 3: "正面-理性看好（低风险）",
# 4: "正面-过度狂热（高风险）"

def _env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _resolve_base_model(default_name: str = "hfl/chinese-roberta-wwm-ext") -> str:
    base_dir = Path(__file__).resolve().parent
    candidates = [
        os.getenv("SENTIMENT_BASE_MODEL_DIR"),
        os.getenv("FINBERT_BASE_MODEL_DIR"),
        base_dir / "chinese-roberta-wwm-ext",
        base_dir / "hfl_chinese-roberta-wwm-ext",
        base_dir / "my_finance_bert_wwm",
    ]
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate).expanduser()
        if path.exists() and (path / "config.json").exists():
            return str(path.resolve())
    return default_name


class FinBERT5Class(BertPreTrainedModel):
    def __init__(self, num_classes=5, model_name='hfl/chinese-roberta-wwm-ext', local_files_only=True):
        config = BertConfig.from_pretrained(model_name, local_files_only=local_files_only)
        super().__init__(config)
        self.bert = BertModel.from_pretrained(model_name, config=config, local_files_only=local_files_only)
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
        self.model_name = _resolve_base_model()
        self.local_files_only = not _env_flag("TRANSFORMERS_ALLOW_ONLINE", False)
        self.MODEL_PATH = str((Path(__file__).resolve().parent / 'finbert_5class_best.pth').resolve())
        self.DEVICE = 'cuda' if torch.cuda.is_available() else 'cpu'
        try:
            self.tokenizer = BertTokenizer.from_pretrained(self.model_name, local_files_only=self.local_files_only)
            self.model = FinBERT5Class(model_name=self.model_name, local_files_only=self.local_files_only)
        except Exception as exc:
            offline_hint = (
                "情感分析模型加载失败。请把 hfl/chinese-roberta-wwm-ext 下载到 "
                "整合/chinese-roberta-wwm-ext，或设置 SENTIMENT_BASE_MODEL_DIR 指向本地模型目录。"
            )
            if self.local_files_only:
                offline_hint += " 当前已禁止联网下载，可临时设置 TRANSFORMERS_ALLOW_ONLINE=1 允许联网。"
            raise RuntimeError(offline_hint) from exc
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
