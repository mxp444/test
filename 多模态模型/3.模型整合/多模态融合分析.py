# -*- coding: utf-8 -*-
"""
本地多模态网络金融舆情风险融合分析。

这个文件负责把已经分开完成的文本模型、图片模型结果接起来，并补上：
1. 文本 / OCR 文本 / 图片视觉的统一特征抽取
2. 跨模态特征融合
3. 一个轻量融合网络层，对融合后的特征向量做最终风险映射

输出字段保持和毕设目录下前后端约定一致：
text_feature_extraction / image_feature_extraction / ocr_text_feature_extraction /
multimodal_feature_fusion / fusion_network_analysis / final_multimodal_analysis
"""

from __future__ import annotations

import importlib
import json
import math
import os
import re
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import jieba
import numpy as np


FINANCE_LABELS = {
    0: "非金融舆情类但胜似金融舆情",
    1: "完全非金融舆情类",
    2: "金融诈骗话术",
    3: "理财经理产品推销",
    4: "客户视角理财分享",
    5: "金融避雷踩坑吐槽",
    6: "A 股股价走势分析",
    7: "金融政策监管动态解读",
    8: "基金定投相关讨论",
    9: "保险产品测评讨论",
    10: "期货贵金属投资讨论",
    11: "数字货币相关舆情",
}

RISK_CATEGORIES = {
    "principal_guarantee": "保本无风险虚假承诺",
    "high_return": "超高收益诱导",
    "pyramid_rebate": "拉人头层级返利",
    "insider_recommendation": "内幕消息违规荐股",
    "urgency_scarcity": "紧迫稀缺营销逼单",
    "authority_endorsement": "虚假资质权威背书",
    "crypto_asset": "虚拟货币/数字资产诈骗",
    "credit_loan": "征信修复/贷款诈骗",
    "private_domain_drainage": "私域引流联系方式",
    "herd_inducement": "虚假造势从众诱导",
    "illegal_foreign_trading": "非法外盘/跨境金融交易",
    "pension_scam": "养老金融诈骗",
    "ponzi_scheme": "资金盘/庞氏骗局特征",
    "entrusted_finance": "代客理财违规操作",
    "nft_metaverse": "数字藏品/元宇宙金融骗局",
    "leverage_allocation": "股票/期货配资违规交易",
}

RISK_KEYWORD_MAP = {
    "principal_guarantee": ["保本", "保息", "稳赚", "稳赚不赔", "无风险", "零风险", "保证收益", "兜底"],
    "high_return": ["高收益", "超高收益", "暴利", "翻倍", "年化", "收益率", "躺赚", "稳赚"],
    "pyramid_rebate": ["下线", "拉新", "返利", "返点", "分红", "代理", "推广", "团队"],
    "insider_recommendation": ["内幕", "内部消息", "荐股", "牛股", "带单", "喊单", "主力", "庄家"],
    "urgency_scarcity": ["限时", "限量", "最后", "名额", "错过不再", "马上", "立即", "倒计时"],
    "authority_endorsement": ["官方", "监管", "批准", "牌照", "资质", "认证", "国资", "托管"],
    "crypto_asset": ["虚拟币", "数字货币", "比特币", "区块链", "币圈", "上链", "挖矿"],
    "credit_loan": ["贷款", "征信", "放款", "额度", "借款", "信用卡", "逾期"],
    "private_domain_drainage": ["微信", "vx", "二维码", "扫码", "私信", "客服", "电话", "加群", "联系"],
    "herd_inducement": ["万人", "大家都", "疯抢", "爆款", "刷屏", "抢购", "火爆", "跟投"],
    "illegal_foreign_trading": ["外汇", "外盘", "境外", "国际黄金", "原油", "杠杆交易"],
    "pension_scam": ["养老", "老年", "养老钱", "康养", "养老项目"],
    "ponzi_scheme": ["资金盘", "庞氏", "复利", "拆分", "静态收益", "动态收益"],
    "entrusted_finance": ["代客理财", "托管账户", "委托操作", "操盘", "收益分成"],
    "nft_metaverse": ["数字藏品", "NFT", "元宇宙", "藏品升值"],
    "leverage_allocation": ["配资", "杠杆", "保证金", "爆仓", "期货配资"],
}

SENTIMENT_LABELS = {
    0: "中性",
    1: "负面-恐慌/恶意唱空（高风险）",
    2: "负面-理性担忧（低风险）",
    3: "正面-理性看好（低风险）",
    4: "正面-过度狂热（高风险）",
}

STOPWORDS = {"", " ", "\n", "\t", "的", "了", "和", "是", "在", "就", "都", "而", "及", "与", "我们", "你们"}


class HeuristicFinancialAttribute:
    def predict_multilabel_topk(self, text: str, k: int = 4) -> List[Tuple[int, float]]:
        text = text or ""
        scores = {idx: 0.02 for idx in FINANCE_LABELS}
        keyword_groups = {
            2: ["高收益", "保本", "拉新", "返利", "下线", "资金盘", "稳赚"],
            3: ["理财", "产品", "经理", "存款", "信托", "基金"],
            4: ["分享", "收益", "配置", "投资经历"],
            5: ["被骗", "踩坑", "避雷", "跑路", "暴雷"],
            6: ["A股", "股票", "大盘", "个股", "板块"],
            7: ["监管", "央行", "政策", "证监会"],
            8: ["基金", "定投", "指数"],
            9: ["保险", "重疾", "寿险"],
            10: ["期货", "黄金", "原油", "贵金属"],
            11: ["比特币", "虚拟币", "数字货币"],
        }
        for idx, words in keyword_groups.items():
            hits = sum(text.count(word) for word in words)
            if hits:
                scores[idx] = min(0.95, 0.2 + hits * 0.18)
        if max(scores.values()) <= 0.02:
            scores[1] = 0.65
        return sorted(scores.items(), key=lambda item: item[1], reverse=True)[:k]


class HeuristicRiskFactor:
    def analyze_text(self, text: str) -> Tuple[Dict[str, List[Dict[str, Any]]], Dict[str, int]]:
        text = text or ""
        details = {}
        summary = {}
        total = 0
        for key, words in RISK_KEYWORD_MAP.items():
            hits = []
            for word in words:
                count = text.count(word)
                if count:
                    hits.append({"word": word, "score": round(min(1.0, 0.35 + count * 0.18), 4)})
                    total += count
            label = RISK_CATEGORIES[key]
            details[label] = hits
            summary[label] = len(hits)
        summary["总风险词数"] = total
        return details, dict(sorted(summary.items(), key=lambda item: item[1], reverse=True))


class HeuristicSentimentAnalysis:
    def predict(self, text: str) -> Dict[str, Any]:
        text = text or ""
        if any(word in text for word in ["暴雷", "崩盘", "跑路", "血亏", "被骗"]):
            label_id = 1
            confidence = 0.82
        elif any(word in text for word in ["稳赚", "暴富", "翻倍", "躺赚", "稳赚不赔"]):
            label_id = 4
            confidence = 0.80
        elif any(word in text for word in ["风险", "谨慎", "波动", "理性"]):
            label_id = 2
            confidence = 0.68
        else:
            label_id = 0
            confidence = 0.55
        return {
            "text": text,
            "sentiment": SENTIMENT_LABELS[label_id],
            "label_id": label_id,
            "risk_level": "高风险" if label_id in {1, 4} else ("低风险" if label_id in {2, 3} else "无风险"),
            "confidence": confidence,
        }


class HeuristicIncitementEvaluator:
    def evaluate(self, text: str) -> Dict[str, Any]:
        text = text or ""
        tone_words = ["绝对", "一定", "马上", "立即", "暴富", "翻倍", "稳赚", "赶紧"]
        scarcity_words = ["限时", "限量", "最后", "名额", "错过不再", "倒计时"]
        herd_words = ["大家都", "万人", "疯抢", "刷屏", "爆款", "抢购"]
        tone = min(40, sum(text.count(w) for w in tone_words) * 8 + (text.count("!") + text.count("！")) * 2)
        scarcity = min(30, sum(text.count(w) for w in scarcity_words) * 8)
        herd = min(30, sum(text.count(w) for w in herd_words) * 10)
        total = tone + scarcity + herd
        return {
            "text": text,
            "total_score": total,
            "risk_level": _incitement_level(total),
            "risk_description": "启发式煽动性评估",
            "dimensions": {
                "tone": {"score": tone, "max_score": 40, "percentage": round(tone / 40 * 100, 1)},
                "scarcity": {"score": scarcity, "max_score": 30, "percentage": round(scarcity / 30 * 100, 1)},
                "herd": {"score": herd, "max_score": 30, "percentage": round(herd / 30 * 100, 1)},
            },
            "recommendation": "建议人工复核" if total >= 40 else "常规监测",
        }


class HeuristicQRDetector:
    def detect_and_decode(self, image_path=None, image_data=None):
        return {"success": True, "qr_detected": False, "qr_data": None, "qr_bbox": None}


class HeuristicAmbiguity:
    def predict(self, image_path):
        return 18.0


class HeuristicColorRichness:
    def image_quality_score(self, image_path, verbose=False):
        if verbose:
            return 55.0, {"total_score": 55.0}
        return 55.0


class FusionNetwork:
    """一个可解释的轻量融合网络：输入融合特征向量，输出多维风险。"""

    hidden_names = [
        "financial_semantic_activation",
        "drainage_activation",
        "marketing_activation",
        "consistency_activation",
        "overall_risk_activation",
    ]
    output_names = ["overall_risk", "financial_risk", "drainage_risk", "marketing_risk", "consistency_risk"]

    def forward(self, feature_names: List[str], values: List[float]) -> Dict[str, Any]:
        x = {name: _norm(value) for name, value in zip(feature_names, values)}
        hidden = {
            "financial_semantic_activation": self._weighted(
                x, {"text_financial_score": 0.35, "ocr_financial_score": 0.25, "finance_synergy": 0.40}
            ),
            "drainage_activation": self._weighted(
                x, {"image_diversion_score": 0.35, "drainage_linkage": 0.45, "qr_detected": 0.20}
            ),
            "marketing_activation": self._weighted(
                x, {"text_incitement_score": 0.25, "ocr_incitement_score": 0.20, "image_visual_marketing_score": 0.25, "persuasion_coupling": 0.30}
            ),
            "consistency_activation": self._weighted(
                x, {"semantic_consistency": 0.35, "risk_alignment": 0.35, "text_image_reinforcement_count": 0.30}
            ),
        }
        hidden["overall_risk_activation"] = self._weighted(
            hidden,
            {
                "financial_semantic_activation": 0.25,
                "drainage_activation": 0.25,
                "marketing_activation": 0.30,
                "consistency_activation": 0.20,
            },
        )
        outputs = {
            "overall_risk": hidden["overall_risk_activation"],
            "financial_risk": hidden["financial_semantic_activation"],
            "drainage_risk": hidden["drainage_activation"],
            "marketing_risk": hidden["marketing_activation"],
            "consistency_risk": hidden["consistency_activation"],
        }
        return {
            "hidden_layer": {name: round(score, 2) for name, score in hidden.items()},
            "output_layer": {name: round(score, 2) for name, score in outputs.items()},
        }

    def _weighted(self, source: Dict[str, float], weights: Dict[str, float]) -> float:
        total_weight = sum(weights.values()) or 1.0
        score = 0.0
        for name, weight in weights.items():
            value = float(source.get(name, 0.0))
            if value > 1.0:
                value = value / 100.0
            score += value * weight
        score = score / total_weight
        # Sigmoid-like sharpening: medium evidence stays medium, strong co-evidence rises faster.
        return _clip((1 / (1 + math.exp(-6 * (score - 0.45)))) * 100, 0, 100)


class MultimodalRiskFusion:
    def __init__(self, base_dir: Optional[str] = None):
        self.base_dir = Path(base_dir or Path(__file__).resolve().parent).resolve()
        self.json_dir = self.base_dir / "json"
        self.component_status: Dict[str, str] = {}
        self.component_load_seconds: Dict[str, float] = {}
        self.init_errors: List[str] = []
        self.fusion_network = FusionNetwork()

        if str(self.base_dir) not in sys.path:
            sys.path.insert(0, str(self.base_dir))

        self.financial_attribute = self._safe_init("nlp金融属性判断", "Financial_attribute", HeuristicFinancialAttribute)
        self.risk_factor = self._safe_init("nlp风险要素识别", "Risk_factor", HeuristicRiskFactor)
        self.sentiment_analysis = self._safe_init("nlp情感分析", "Sentiment_analysis", HeuristicSentimentAnalysis)
        self.incitement_evaluator = self._safe_init("nlp煽动性评估", "Incitement_evaluator", HeuristicIncitementEvaluator)
        self.qr_code_detector = self._safe_init("pic二维码检测", "QR_code_detector", HeuristicQRDetector)
        self.ambiguity = self._safe_init("pic模糊度检测", "Ambiguity", HeuristicAmbiguity)
        self.color_richness = self._safe_init("pic色彩丰富程度", "Color_richness", HeuristicColorRichness)
        self.design_sense = self._safe_init("pic设计感", "Design_sense", None, record_error=False)

    def analyze(self, post_text: str, image_path: str) -> Dict[str, Any]:
        image_file = self._resolve_image_path(image_path)
        if not image_file.exists():
            raise FileNotFoundError(f"图片不存在: {image_file}")

        text_result = self._analyze_text(post_text, source="post_text")
        image_result = self._analyze_image(image_file)
        ocr_text = image_result.get("ocr_text", "")
        ocr_result = self._analyze_text(ocr_text, source="ocr_text") if ocr_text else self._empty_text_result("ocr_text")
        fusion = self._fuse_modalities(text_result, image_result, ocr_result)
        network = self._run_fusion_network(fusion)
        final = self._final_decision(text_result, image_result, ocr_result, fusion, network)

        return _to_jsonable({
            "input": {"post_text": post_text, "image_path": str(image_file)},
            "runtime": {
                "component_status": self.component_status,
                "component_load_seconds": self.component_load_seconds,
                "init_errors": self.init_errors,
            },
            "text_feature_extraction": text_result,
            "image_feature_extraction": image_result,
            "ocr_text_feature_extraction": ocr_result,
            "multimodal_feature_fusion": fusion,
            "fusion_network_analysis": network,
            "final_multimodal_analysis": final,
        })

    def analyze_batch(self, items: Iterable[Dict[str, str]]) -> List[Dict[str, Any]]:
        return [self.analyze(item.get("post_text", ""), item.get("image_path", "")) for item in items]

    def _analyze_text(self, text: str, source: str) -> Dict[str, Any]:
        text = text or ""
        with self._working_directory():
            finance_topk_raw = self.financial_attribute.predict_multilabel_topk(text, k=4)
            risk_details_raw, risk_summary = self.risk_factor.analyze_text(text)
            sentiment = self.sentiment_analysis.predict(text)
            incitement = self.incitement_evaluator.evaluate(text)

        finance_topk = self._normalize_finance_topk(finance_topk_raw)
        risk_factor_scores = self._risk_factor_scores(text, risk_details_raw, risk_summary)
        financial_score = self._financial_score(finance_topk)
        risk_factor_score = _clip(sum(risk_factor_scores.values()) / max(len(risk_factor_scores), 1) * 1.6, 0, 100)
        sentiment_score = self._sentiment_score(sentiment)
        incitement_score = _clip(float(incitement.get("total_score", 0)), 0, 100)
        overall_score = round(
            0.22 * financial_score + 0.34 * risk_factor_score + 0.18 * sentiment_score + 0.26 * incitement_score,
            2,
        )

        evidence = []
        top_risks = sorted(risk_factor_scores.items(), key=lambda item: item[1], reverse=True)[:5]
        for key, score in top_risks:
            if score >= 35:
                evidence.append(f"{source} 命中风险要素：{RISK_CATEGORIES[key]}，得分 {score:.1f}")
        if incitement_score >= 40:
            evidence.append(f"{source} 煽动性得分较高：{incitement_score:.1f}")
        if sentiment.get("risk_level") == "高风险":
            evidence.append(f"{source} 情绪模型判定为高风险情绪，置信度 {sentiment.get('confidence')}")

        return {
            "finance_topk": finance_topk,
            "risk_factor_scores": {key: round(value, 2) for key, value in risk_factor_scores.items()},
            "risk_factor_summary": risk_summary,
            "risk_factor_details": risk_details_raw,
            "sentiment": sentiment,
            "incitement": {
                "tone_score": self._dimension_score(incitement, "tone"),
                "scarcity_score": self._dimension_score(incitement, "scarcity"),
                "herd_score": self._dimension_score(incitement, "herd"),
                "total_score": round(incitement_score, 2),
                "risk_level": incitement.get("risk_level", _incitement_level(incitement_score)),
                "raw": incitement,
            },
            "scores": {
                "financial_score": round(financial_score, 2),
                "risk_factor_score": round(risk_factor_score, 2),
                "sentiment_score": round(sentiment_score, 2),
                "incitement_score": round(incitement_score, 2),
                "overall_score": overall_score,
            },
            "raw_text": text,
            "evidence": evidence,
        }

    def _analyze_image(self, image_path: Path) -> Dict[str, Any]:
        errors = []
        with self._working_directory():
            qr_result = self._call_image_component(
                "二维码检测", lambda: self.qr_code_detector.detect_and_decode(str(image_path)), errors, {}
            )
            blur_raw = self._call_image_component("模糊度检测", lambda: float(self.ambiguity.predict(str(image_path))), errors, 18.0)
            color_score = self._call_image_component(
                "色彩丰富度检测", lambda: float(self.color_richness.image_quality_score(str(image_path))), errors, 55.0
            )
            design_score = None
            design_std = None
            if self.design_sense is not None:
                try:
                    mean, std = self.design_sense.predict(str(image_path))
                    design_score = round(_clip(float(mean) * 10, 0, 100), 2)
                    design_std = round(float(std), 4)
                except Exception as exc:
                    errors.append(f"设计感检测失败: {exc}")

        qr_result = qr_result if isinstance(qr_result, dict) else {}
        ocr_text = self._load_cached_ocr_text(image_path)
        clarity_score = self._normalize_blur(blur_raw)
        visual_marketing_score = self._visual_marketing_score(color_score, clarity_score, design_score)
        financial_visual_score = self._financial_visual_score(ocr_text)
        contact_detected = self._contact_detected(ocr_text)
        diversion_score = self._diversion_score(qr_result, ocr_text)
        overall_score = round(0.35 * visual_marketing_score + 0.30 * financial_visual_score + 0.35 * diversion_score, 2)

        evidence = []
        if qr_result.get("qr_detected"):
            evidence.append("图片检测到二维码，存在跳转或私域引流可能")
        if contact_detected:
            evidence.append("图片 OCR 文本中出现联系方式或引流表达")
        if financial_visual_score >= 45:
            evidence.append(f"图片 OCR/视觉内容指向金融主题，得分 {financial_visual_score:.1f}")
        if not ocr_text:
            evidence.append("未读取到缓存 OCR 文本，图片文字风险仅基于视觉指标与二维码检测")
        evidence.extend(errors[:3])

        return {
            "ocr_text": ocr_text,
            "qr_result": {
                "qr_detected": bool(qr_result.get("qr_detected")),
                "qr_data": qr_result.get("qr_data"),
                "qr_bbox": qr_result.get("qr_bbox"),
            },
            "visual_tags": self._visual_tags(ocr_text, qr_result, visual_marketing_score, financial_visual_score),
            "contact_detected": contact_detected,
            "visual_marketing_score": round(visual_marketing_score, 2),
            "financial_visual_score": round(financial_visual_score, 2),
            "scores": {
                "diversion_score": round(diversion_score, 2),
                "visual_marketing_score": round(visual_marketing_score, 2),
                "financial_visual_score": round(financial_visual_score, 2),
                "overall_score": round(overall_score, 2),
            },
            "visual_metrics": {
                "blur_raw": round(float(blur_raw), 4),
                "clarity_score": round(clarity_score, 2),
                "color_score": round(float(color_score), 2),
                "design_score": design_score,
                "design_std": design_std,
            },
            "evidence": evidence,
        }

    def _fuse_modalities(self, text_result: Dict[str, Any], image_result: Dict[str, Any], ocr_result: Dict[str, Any]) -> Dict[str, Any]:
        text_score = float(text_result["scores"]["overall_score"])
        image_score = float(image_result["scores"]["overall_score"])
        ocr_score = float(ocr_result["scores"]["overall_score"])

        semantic_consistency, shared_keywords = self._semantic_consistency(text_result.get("raw_text", ""), image_result.get("ocr_text", ""))
        risk_alignment, shared_risk_categories = self._risk_alignment(text_result, ocr_result)
        finance_synergy = self._finance_synergy(text_result, image_result, ocr_result)
        drainage_linkage = self._drainage_linkage(text_result, image_result, ocr_result)
        persuasion_coupling = self._persuasion_coupling(text_result, image_result, ocr_result)
        reinforcement = self._text_image_reinforcement(text_result, image_result, ocr_result)
        contradictions = self._contradictions(text_result, image_result, ocr_result)

        feature_names, values = self._build_feature_vector(
            text_result,
            image_result,
            ocr_result,
            semantic_consistency,
            risk_alignment,
            finance_synergy,
            drainage_linkage,
            persuasion_coupling,
            len(reinforcement),
        )
        weights = self._modality_weights(text_score, image_score, ocr_score, semantic_consistency, drainage_linkage)
        breakdown = {
            "post_text_score": round(text_score, 2),
            "image_score": round(image_score, 2),
            "ocr_text_score": round(ocr_score, 2),
            "cross_modal_score": round(
                0.20 * semantic_consistency + 0.25 * risk_alignment + 0.20 * finance_synergy + 0.20 * drainage_linkage + 0.15 * persuasion_coupling,
                2,
            ),
        }

        return {
            "fusion_method": "text_features + image_features + ocr_features + cross_modal_interaction",
            "cross_modal_features": {
                "semantic_consistency": round(semantic_consistency, 2),
                "risk_alignment": round(risk_alignment, 2),
                "finance_synergy": round(finance_synergy, 2),
                "drainage_linkage": round(drainage_linkage, 2),
                "persuasion_coupling": round(persuasion_coupling, 2),
                "shared_keywords": shared_keywords,
                "shared_risk_categories": shared_risk_categories,
                "text_image_reinforcement": reinforcement,
                "contradictions": contradictions,
            },
            "fused_feature_vector": {"feature_names": feature_names, "values": [round(value, 4) for value in values]},
            "modality_weights": weights,
            "modality_breakdown": breakdown,
        }

    def _run_fusion_network(self, fusion: Dict[str, Any]) -> Dict[str, Any]:
        vector = fusion["fused_feature_vector"]
        network = self.fusion_network.forward(vector["feature_names"], vector["values"])
        return {
            "network_structure": "输入融合特征向量 -> 隐含风险表征层 -> 多维风险输出层",
            "input_layer": {
                "feature_count": len(vector["feature_names"]),
                "feature_names": vector["feature_names"],
                "values": vector["values"],
            },
            "hidden_layer": network["hidden_layer"],
            "output_layer": network["output_layer"],
        }

    def _final_decision(
        self,
        text_result: Dict[str, Any],
        image_result: Dict[str, Any],
        ocr_result: Dict[str, Any],
        fusion: Dict[str, Any],
        network: Dict[str, Any],
    ) -> Dict[str, Any]:
        output = network["output_layer"]
        total_score = round(float(output.get("overall_risk", 0)), 2)
        risk_level = _final_level(total_score)
        reasons = []
        reasons.extend(text_result.get("evidence", [])[:4])
        reasons.extend(image_result.get("evidence", [])[:4])
        reasons.extend(ocr_result.get("evidence", [])[:3])
        cross = fusion["cross_modal_features"]
        if cross["drainage_linkage"] >= 50:
            reasons.append(f"图文/二维码/联系方式形成引流联动，联动得分 {cross['drainage_linkage']:.1f}")
        if cross["persuasion_coupling"] >= 50:
            reasons.append(f"文本煽动性与视觉营销信号耦合，耦合得分 {cross['persuasion_coupling']:.1f}")
        if not reasons:
            reasons.append("未发现明确诈骗、引流或夸大收益证据，按低风险处理")

        return {
            "total_score": total_score,
            "risk_level": risk_level,
            "conclusion": self._conclusion(total_score, cross),
            "reasons": reasons[:10],
            "suggestion": self._suggestion(total_score),
        }

    def _normalize_finance_topk(self, topk_raw: Iterable[Any]) -> List[Dict[str, Any]]:
        result = []
        for label, confidence in topk_raw or []:
            try:
                label_id = int(label)
            except (TypeError, ValueError):
                label_id = self._label_id_from_name(str(label))
            result.append(
                {
                    "label_id": label_id,
                    "label": FINANCE_LABELS.get(label_id, str(label)),
                    "confidence": round(float(confidence), 4),
                }
            )
        return result[:4]

    def _risk_factor_scores(self, text: str, risk_details: Dict[str, Any], risk_summary: Dict[str, Any]) -> Dict[str, float]:
        scores = {}
        for key, label in RISK_CATEGORIES.items():
            keyword_hits = sum(text.count(word) for word in RISK_KEYWORD_MAP.get(key, []))
            detail_hits = len(risk_details.get(label, [])) if isinstance(risk_details, dict) else 0
            summary_hits = int(risk_summary.get(label, 0)) if isinstance(risk_summary, dict) and str(risk_summary.get(label, 0)).isdigit() else 0
            hits = max(keyword_hits, detail_hits, summary_hits)
            scores[key] = _clip(hits * 22, 0, 100)
        return scores

    def _build_feature_vector(
        self,
        text_result: Dict[str, Any],
        image_result: Dict[str, Any],
        ocr_result: Dict[str, Any],
        semantic_consistency: float,
        risk_alignment: float,
        finance_synergy: float,
        drainage_linkage: float,
        persuasion_coupling: float,
        reinforcement_count: int,
    ) -> Tuple[List[str], List[float]]:
        text_scores = text_result["scores"]
        image_scores = image_result["scores"]
        ocr_scores = ocr_result["scores"]
        feature_map = {
            "text_financial_score": text_scores["financial_score"],
            "text_risk_factor_score": text_scores["risk_factor_score"],
            "text_sentiment_score": text_scores["sentiment_score"],
            "text_incitement_score": text_scores["incitement_score"],
            "text_overall_score": text_scores["overall_score"],
            "image_diversion_score": image_scores["diversion_score"],
            "image_visual_marketing_score": image_scores["visual_marketing_score"],
            "image_financial_visual_score": image_scores["financial_visual_score"],
            "image_overall_score": image_scores["overall_score"],
            "ocr_financial_score": ocr_scores["financial_score"],
            "ocr_risk_factor_score": ocr_scores["risk_factor_score"],
            "ocr_sentiment_score": ocr_scores["sentiment_score"],
            "ocr_incitement_score": ocr_scores["incitement_score"],
            "ocr_overall_score": ocr_scores["overall_score"],
            "semantic_consistency": semantic_consistency,
            "risk_alignment": risk_alignment,
            "finance_synergy": finance_synergy,
            "drainage_linkage": drainage_linkage,
            "persuasion_coupling": persuasion_coupling,
            "text_image_reinforcement_count": min(reinforcement_count * 25, 100),
            "qr_detected": 100.0 if image_result.get("qr_result", {}).get("qr_detected") else 0.0,
        }
        names = list(feature_map.keys())
        return names, [round(float(feature_map[name]), 4) for name in names]

    def _safe_init(self, module_name: str, class_name: str, fallback_cls, record_error: bool = True):
        component_name = f"{module_name}.{class_name}"
        start = time.perf_counter()
        try:
            with self._working_directory():
                module = importlib.import_module(module_name)
                instance = getattr(module, class_name)()
            self.component_status[component_name] = "model"
            self.component_load_seconds[component_name] = round(time.perf_counter() - start, 3)
            return instance
        except Exception as exc:
            if fallback_cls is not None:
                self.component_status[component_name] = "fallback"
                self.component_load_seconds[component_name] = round(time.perf_counter() - start, 3)
                self.init_errors.append(f"{component_name}: {exc}")
                return fallback_cls()
            if record_error:
                self.component_status[component_name] = "unavailable"
                self.component_load_seconds[component_name] = round(time.perf_counter() - start, 3)
                self.init_errors.append(f"{component_name}: {exc}")
            return None

    def _working_directory(self):
        return _pushd(self.base_dir)

    def _resolve_image_path(self, image_path: str) -> Path:
        candidate = Path(image_path).expanduser()
        if candidate.is_absolute():
            return candidate.resolve()
        return (self.base_dir / candidate).resolve()

    def _load_cached_ocr_text(self, image_path: Path) -> str:
        candidates = [
            self.json_dir / f"{image_path.name}.json",
            image_path.with_suffix(image_path.suffix + ".json"),
            self.base_dir / f"{image_path.name}.json",
            Path.cwd() / f"{image_path.name}.json",
        ]
        for json_path in candidates:
            if not json_path.exists():
                continue
            try:
                data = json.loads(json_path.read_text(encoding="utf-8"))
                items = data.get("ocrResult") or data.get("ocr_result") or data.get("items") or []
                texts = [str(item.get("text", "")).strip() for item in items if isinstance(item, dict) and item.get("text")]
                if texts:
                    return "\n".join(texts).strip()
            except Exception:
                continue
        return ""

    def _call_image_component(self, name: str, fn, errors: List[str], default):
        try:
            return fn()
        except Exception as exc:
            errors.append(f"{name}失败: {exc}")
            return default

    def _financial_score(self, finance_topk: List[Dict[str, Any]]) -> float:
        if not finance_topk:
            return 0.0
        label_id = finance_topk[0]["label_id"]
        confidence = float(finance_topk[0]["confidence"])
        if label_id == 1:
            base = 15
        elif label_id in {2, 11, 10}:
            base = 85
        elif label_id in {0, 3, 5, 6, 7, 8, 9}:
            base = 62
        else:
            base = 48
        return _clip(base * (0.45 + 0.55 * confidence), 0, 100)

    def _sentiment_score(self, sentiment: Dict[str, Any]) -> float:
        label_id = sentiment.get("label_id")
        confidence = float(sentiment.get("confidence", 0.0))
        base = 85 if label_id in {1, 4} else (35 if label_id in {2, 3} else 15)
        return _clip(base * (0.55 + 0.45 * confidence), 0, 100)

    def _dimension_score(self, incitement: Dict[str, Any], name: str) -> float:
        return round(float(incitement.get("dimensions", {}).get(name, {}).get("score", 0)), 2)

    def _normalize_blur(self, blur_raw: float) -> float:
        return round(_clip(float(blur_raw) / 35 * 100, 0, 100), 2)

    def _visual_marketing_score(self, color_score: float, clarity_score: float, design_score: Optional[float]) -> float:
        if design_score is None:
            return round(0.55 * float(color_score) + 0.45 * float(clarity_score), 2)
        return round(0.30 * float(color_score) + 0.25 * float(clarity_score) + 0.45 * float(design_score), 2)

    def _financial_visual_score(self, ocr_text: str) -> float:
        hits = sum(ocr_text.count(word) for words in RISK_KEYWORD_MAP.values() for word in words)
        finance_words = ["金融", "理财", "基金", "保险", "股票", "期货", "收益", "投资", "贷款", "数字货币"]
        hits += sum(ocr_text.count(word) for word in finance_words)
        return _clip(hits * 12, 0, 100)

    def _contact_detected(self, text: str) -> bool:
        return bool(re.search(r"微信|vx|v信|qq|二维码|扫码|私信|客服|电话|手机|网址|http|www|加群|联系", text or "", re.I))

    def _diversion_score(self, qr_result: Dict[str, Any], ocr_text: str) -> float:
        score = 75 if qr_result.get("qr_detected") else 0
        if self._contact_detected(ocr_text):
            score += 30
        return _clip(score, 0, 100)

    def _visual_tags(self, ocr_text: str, qr_result: Dict[str, Any], visual_marketing_score: float, financial_visual_score: float) -> List[str]:
        tags = []
        if qr_result.get("qr_detected"):
            tags.append("二维码")
        if self._contact_detected(ocr_text):
            tags.append("联系方式/私域引流")
        if financial_visual_score >= 40:
            tags.append("金融主题")
        if visual_marketing_score >= 60:
            tags.append("营销海报风格")
        return tags

    def _semantic_consistency(self, text_a: str, text_b: str) -> Tuple[float, List[str]]:
        tokens_a = self._tokens(text_a)
        tokens_b = self._tokens(text_b)
        if not tokens_a or not tokens_b:
            return 0.0, []
        shared = sorted(tokens_a & tokens_b)
        ratio = len(shared) / max(min(len(tokens_a), len(tokens_b)), 1)
        return round(_clip(ratio * 100, 0, 100), 2), shared[:20]

    def _risk_alignment(self, text_result: Dict[str, Any], ocr_result: Dict[str, Any]) -> Tuple[float, List[str]]:
        text_positive = {RISK_CATEGORIES[k] for k, v in text_result.get("risk_factor_scores", {}).items() if v >= 30}
        ocr_positive = {RISK_CATEGORIES[k] for k, v in ocr_result.get("risk_factor_scores", {}).items() if v >= 30}
        shared = sorted(text_positive & ocr_positive)
        if not text_positive or not ocr_positive:
            return 0.0, shared
        return round(len(shared) / max(min(len(text_positive), len(ocr_positive)), 1) * 100, 2), shared

    def _finance_synergy(self, text_result: Dict[str, Any], image_result: Dict[str, Any], ocr_result: Dict[str, Any]) -> float:
        values = [
            text_result["scores"]["financial_score"],
            image_result["scores"]["financial_visual_score"],
            ocr_result["scores"]["financial_score"],
        ]
        active = [value for value in values if value >= 40]
        if len(active) >= 2:
            return _clip(sum(active) / len(active) + 10, 0, 100)
        return _clip(max(values) * 0.55, 0, 100)

    def _drainage_linkage(self, text_result: Dict[str, Any], image_result: Dict[str, Any], ocr_result: Dict[str, Any]) -> float:
        text_drainage = text_result["risk_factor_scores"].get("private_domain_drainage", 0)
        ocr_drainage = ocr_result["risk_factor_scores"].get("private_domain_drainage", 0)
        image_drainage = image_result["scores"]["diversion_score"]
        return _clip(0.35 * max(text_drainage, ocr_drainage) + 0.65 * image_drainage, 0, 100)

    def _persuasion_coupling(self, text_result: Dict[str, Any], image_result: Dict[str, Any], ocr_result: Dict[str, Any]) -> float:
        text_incite = text_result["scores"]["incitement_score"]
        ocr_incite = ocr_result["scores"]["incitement_score"]
        visual = image_result["scores"]["visual_marketing_score"]
        return _clip(0.40 * max(text_incite, ocr_incite) + 0.60 * visual, 0, 100)

    def _text_image_reinforcement(self, text_result: Dict[str, Any], image_result: Dict[str, Any], ocr_result: Dict[str, Any]) -> List[str]:
        items = []
        if text_result["scores"]["financial_score"] >= 45 and image_result["scores"]["financial_visual_score"] >= 35:
            items.append("正文金融主题与图片金融元素相互强化")
        if max(text_result["scores"]["incitement_score"], ocr_result["scores"]["incitement_score"]) >= 40 and image_result["scores"]["visual_marketing_score"] >= 55:
            items.append("煽动性话术与营销式视觉呈现相互强化")
        if image_result["scores"]["diversion_score"] >= 60 and text_result["risk_factor_scores"].get("private_domain_drainage", 0) >= 30:
            items.append("正文引流词与图片二维码/联系方式相互强化")
        return items

    def _contradictions(self, text_result: Dict[str, Any], image_result: Dict[str, Any], ocr_result: Dict[str, Any]) -> List[str]:
        items = []
        if text_result["scores"]["overall_score"] < 25 and image_result["scores"]["overall_score"] >= 70:
            items.append("正文风险较低但图片存在明显引流或营销风险")
        if text_result["scores"]["overall_score"] >= 70 and image_result["scores"]["overall_score"] < 25:
            items.append("正文风险较高但图片未提供对应视觉证据")
        return items

    def _modality_weights(self, text_score: float, image_score: float, ocr_score: float, semantic: float, drainage: float) -> Dict[str, float]:
        weights = {
            "text": 0.38 + (0.06 if text_score >= 60 else 0),
            "image": 0.24 + (0.08 if image_score >= 60 else 0),
            "ocr_text": 0.20 + (0.06 if ocr_score >= 40 else 0),
            "cross_modal": 0.18 + (0.08 if semantic >= 40 or drainage >= 50 else 0),
        }
        total = sum(weights.values()) or 1
        return {key: round(value / total, 4) for key, value in weights.items()}

    def _tokens(self, text: str) -> set:
        tokens = set()
        for token in jieba.lcut(text or ""):
            token = token.strip().lower()
            if len(token) < 2 or token in STOPWORDS or re.fullmatch(r"[\W_]+", token):
                continue
            tokens.add(token)
        return tokens

    def _label_id_from_name(self, label: str) -> int:
        for idx, name in FINANCE_LABELS.items():
            if label == name or label in name or name in label:
                return idx
        return 0

    def _empty_text_result(self, source: str) -> Dict[str, Any]:
        return {
            "finance_topk": [],
            "risk_factor_scores": {key: 0.0 for key in RISK_CATEGORIES},
            "risk_factor_summary": {},
            "risk_factor_details": {},
            "sentiment": {},
            "incitement": {"tone_score": 0.0, "scarcity_score": 0.0, "herd_score": 0.0, "total_score": 0.0, "risk_level": "无风险"},
            "scores": {"financial_score": 0.0, "risk_factor_score": 0.0, "sentiment_score": 0.0, "incitement_score": 0.0, "overall_score": 0.0},
            "raw_text": "",
            "evidence": [f"{source} 为空，未参与文本风险计算"],
        }

    def _conclusion(self, score: float, cross: Dict[str, Any]) -> str:
        if score >= 80:
            return "样本呈现高风险多模态金融舆情特征，文本、图片或 OCR 之间存在明显风险强化关系。"
        if score >= 60:
            return "样本存在较明显风险信号，建议重点关注收益承诺、引流方式和视觉营销耦合。"
        if score >= 40:
            return "样本存在部分金融风险线索，但跨模态强化程度有限，建议结合传播账号继续观察。"
        return "样本整体风险较低，暂未形成明确的多模态高风险证据链。"

    def _suggestion(self, score: float) -> str:
        if score >= 80:
            return "建议立即进入人工复核，核查二维码、联系方式、收益承诺和资质背书。"
        if score >= 60:
            return "建议标记为重点关注样本，并补充账号历史、评论互动和外链去向分析。"
        if score >= 40:
            return "建议常规监测并保留证据，若后续传播扩大再提高处置优先级。"
        return "建议保持常规监测。"


@contextmanager
def _pushd(path: Path):
    current = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(current)


def _clip(value: float, low: float, high: float) -> float:
    return max(low, min(float(value), high))


def _norm(value: float) -> float:
    return _clip(float(value), 0, 100) / 100.0


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, np.ndarray):
        return _to_jsonable(value.tolist())
    if isinstance(value, np.generic):
        return value.item()
    return value


def _incitement_level(score: float) -> str:
    if score >= 80:
        return "极高风险"
    if score >= 60:
        return "高风险"
    if score >= 40:
        return "中等风险"
    if score >= 20:
        return "低风险"
    return "无风险"


def _final_level(score: float) -> str:
    if score >= 80:
        return "高风险"
    if score >= 60:
        return "中高风险"
    if score >= 40:
        return "中风险"
    return "低风险"


AliyunRiskAnalyzer = MultimodalRiskFusion
ChatGPTRiskAnalyzer = MultimodalRiskFusion


if __name__ == "__main__":
    demo_text = "限时福利，扫码添加客服领取投资资料，内部渠道推荐高收益理财方案，机会难得，错过不再。"
    demo_image = "pics/f97c511ba970ba119590ad18aec2e0b5.jpeg"
    analyzer = MultimodalRiskFusion()
    result = analyzer.analyze(demo_text, demo_image)
    print(json.dumps(result, ensure_ascii=False, indent=2))
