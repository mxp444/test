# -*- coding: utf-8 -*-
"""
Aliyun API backed multimodal fusion analysis.

This file is self-contained: backend/app.py loads this module directly for API
analysis and does not import the project-root main.py.

Public interface kept compatible with the local analyzer:
- class ``MultimodalRiskFusion``
- ``analyze(post_text: str, image_path: str) -> dict``
- ``analyze_batch(items) -> list[dict]``
"""

from __future__ import annotations

import base64
import json
import mimetypes
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from encoding_guard import install_encoding_guard

install_encoding_guard()

DEFAULT_MODEL = "qwen3-vl-flash-2025-10-15"
ALIYUN_BASE_URL = os.getenv(
    "DASHSCOPE_BASE_URL",
    os.getenv("ALIYUN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
).rstrip("/")
ALIYUN_CHAT_COMPLETIONS_URL = f"{ALIYUN_BASE_URL}/chat/completions"
BASE_DIR = Path(__file__).resolve().parent


FINANCE_LABELS = {
    0: "非金融舆情类但貌似金融舆情",
    1: "完全非金融舆情类",
    2: "金融诈骗话术",
    3: "理财经理产品推销",
    4: "客户视角理财分享",
    5: "金融避雷踩坑吐槽",
    6: "A股股价走势分析",
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


SENTIMENT_LABELS = {
    0: "中性",
    1: "负面-恐慌/恶意唱空（高风险）",
    2: "负面-理性担忧（低风险）",
    3: "正面-理性看好（低风险）",
    4: "正面-过度狂热（高风险）",
}


INCITEMENT_LEVELS = {
    "无风险": "0 <= total_score < 20",
    "低风险": "20 <= total_score < 40",
    "中等风险": "40 <= total_score < 60",
    "高风险": "60 <= total_score < 80",
    "极高风险": "80 <= total_score <= 100",
}


FINAL_RISK_LEVELS = {
    "低风险": "0 <= total_score < 30",
    "中风险": "30 <= total_score < 50",
    "中高风险": "50 <= total_score < 70",
    "高风险": "70 <= total_score <= 100",
}


class AliyunMultimodalRiskAnalyzer:
    """Ask Qwen-VL to complete feature extraction, fusion, network-layer analysis, and final judgment."""

    def __init__(self, api_key: Optional[str] = None, model: str = DEFAULT_MODEL):
        self.api_key = "sk-06c74bb0efd248c1bce84d1dc3658e37"
        self.model = model
        if not self.api_key:
            raise RuntimeError(
                "缺少 DASHSCOPE_API_KEY。请先在阿里云百炼创建 API Key，"
                "然后在 PowerShell 中执行：$env:DASHSCOPE_API_KEY='你的Key'"
            )

    def analyze(self, post_text: str, image_path: str) -> Dict[str, Any]:
        image_file = self._resolve_image_path(image_path)
        if not image_file.exists():
            raise FileNotFoundError(f"图片不存在: {image_file}")

        response, request_metrics = self._post_chat_completion(post_text=post_text, image_path=image_file)
        result = self._extract_json(response)
        result.setdefault("input", {"post_text": post_text, "image_path": str(image_file)})
        runtime = result.setdefault(
            "runtime",
            {
                "component_status": {
                    "aliyun.bailian.qwen_vl": self.model,
                    "feature_extraction": "model",
                    "feature_fusion": "model",
                    "fusion_network_analysis": "model",
                },
                "init_errors": [],
            },
        )
        runtime["aliyun_remote_elapsed_seconds"] = round(request_metrics["total_elapsed_seconds"], 3)
        runtime["aliyun_remote_elapsed_ms"] = round(request_metrics["total_elapsed_seconds"] * 1000, 1)
        if request_metrics.get("first_content_elapsed_seconds") is not None:
            runtime["aliyun_first_content_elapsed_seconds"] = round(request_metrics["first_content_elapsed_seconds"], 3)
            runtime["aliyun_first_content_elapsed_ms"] = round(request_metrics["first_content_elapsed_seconds"] * 1000, 1)
        return result

    def _post_chat_completion(self, post_text: str, image_path: Path) -> Tuple[Dict[str, Any], Dict[str, Optional[float]]]:
        payload = self._build_payload(post_text, image_path)
        payload["stream"] = True
        request = urllib.request.Request(
            ALIYUN_CHAT_COMPLETIONS_URL,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
            },
            method="POST",
        )

        try:
            print(f"[timer] Sending API request: {ALIYUN_CHAT_COMPLETIONS_URL}")
            start_time = time.perf_counter()
            with urllib.request.urlopen(request, timeout=120) as response:
                content = self._read_streaming_content(response)
            elapsed_seconds = time.perf_counter() - start_time
            print(f"[timer] API response received in {elapsed_seconds:.3f}s ({elapsed_seconds * 1000:.1f} ms)")
            return (
                {"choices": [{"message": {"content": content}}]},
                {
                    "first_content_elapsed_seconds": None,
                    "total_elapsed_seconds": elapsed_seconds,
                },
            )
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"阿里云百炼 API 请求失败: HTTP {exc.code} {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"阿里云百炼 API 请求失败: {exc}") from exc

    def _read_streaming_content(self, response: Any) -> str:
        content_parts = []
        raw_events = []
        for raw_line in response:
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line or line.startswith(":") or not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            if len(raw_events) < 5:
                raw_events.append(data[:500])
            try:
                chunk = json.loads(data)
            except json.JSONDecodeError:
                continue
            if chunk.get("error"):
                raise RuntimeError(f"阿里云百炼流式响应错误: {json.dumps(chunk.get('error'), ensure_ascii=False)}")
            choice = (chunk.get("choices") or [{}])[0]
            delta = choice.get("delta") or {}
            message = choice.get("message") or {}
            piece = delta.get("content", "")
            if not piece:
                piece = message.get("content", "")
            if isinstance(piece, list):
                piece = "".join(
                    item.get("text", "") if isinstance(item, dict) else str(item)
                    for item in piece
                )
            if piece:
                content_parts.append(str(piece))
        content = "".join(content_parts)
        if not content.strip():
            preview = " | ".join(raw_events) if raw_events else "<no data events>"
            raise RuntimeError(f"阿里云百炼流式响应没有正文内容，模型可能不兼容 chat/completions。raw={preview}")
        return content

    def _build_payload(self, post_text: str, image_path: Path) -> Dict[str, Any]:
        return {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是多模态网络金融舆情风险监测算法。你必须在用户给定的标签体系和评分准则内，"
                        "完成文本、图像分析和多模态融合分析。只输出合法 JSON。"
                    ),
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": self._build_prompt(post_text)},
                        {"type": "image_url", "image_url": {"url": self._image_to_data_url(image_path)}},
                    ],
                },
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.0,
            "max_tokens": 8192,
        }

    def _build_prompt(self, post_text: str) -> str:
        finance_top4_template = [
            {"label_id": 0, "label": "从FINANCE_LABELS中选择", "confidence": 0.0},
            {"label_id": 0, "label": "从FINANCE_LABELS中选择", "confidence": 0.0},
            {"label_id": 0, "label": "从FINANCE_LABELS中选择", "confidence": 0.0},
            {"label_id": 0, "label": "从FINANCE_LABELS中选择", "confidence": 0.0},
        ]
        risk_factor_scores_template = {key: 0.0 for key in RISK_CATEGORIES}
        risk_factor_details_template = {
            key: {
                "category_label": label,
                "category_score": 0.0,
                "matched_terms": [],
                "term_count": 0,
            }
            for key, label in RISK_CATEGORIES.items()
        }
        risk_factor_summary_template = {
            "category_counts": {key: 0 for key in RISK_CATEGORIES},
            "positive_category_count": 0,
            "total_risk_word_count": 0,
        }
        sentiment_template = {
            "label_id": 0,
            "label": "从SENTIMENT_LABELS中选择",
            "risk_level": "由label_id按情感风险映射得到",
            "confidence": 0.0,
        }
        incitement_template = {
            "text": "",
            "total_score": 0.0,
            "risk_level": "从INCITEMENT_LEVELS中选择",
            "risk_description": "",
            "tone_score": 0.0,
            "scarcity_score": 0.0,
            "herd_score": 0.0,
            "dimensions": {
                "tone": {
                    "score": 0.0,
                    "max_score": 40,
                    "percentage": 0.0,
                    "details": {
                        "exclamation_count": 0,
                        "extreme_words_found": [],
                        "all_caps_ratio": 0.0,
                        "repeated_punctuation": [],
                    },
                },
                "scarcity": {
                    "score": 0.0,
                    "max_score": 30,
                    "percentage": 0.0,
                    "details": {
                        "matched_patterns": [],
                        "urgency_phrases": [],
                        "numbers_detected": [],
                    },
                },
                "herd": {
                    "score": 0.0,
                    "max_score": 30,
                    "percentage": 0.0,
                    "details": {
                        "matched_patterns": [],
                        "numbers_detected": [],
                        "social_proof_phrases": [],
                    },
                },
            },
            "recommendation": "",
        }
        text_analysis_template = {
            "finance_topk": finance_top4_template,
            "risk_factor_scores": risk_factor_scores_template,
            "risk_factor_details": risk_factor_details_template,
            "risk_factor_summary": risk_factor_summary_template,
            "sentiment": sentiment_template,
            "incitement": incitement_template,
            "scores": {
                "financial_score": 0.0,
                "risk_factor_score": 0.0,
                "sentiment_score": 0.0,
                "incitement_score": 0.0,
                "overall_score": 0.0,
            },
            "evidence": [],
        }
        output_template = {
            "input": {"post_text": post_text, "image_path": ""},
            "runtime": {
                "component_status": {
                    "feature_extraction": "model",
                    "feature_fusion": "model",
                    "fusion_network_analysis": "model",
                },
                "init_errors": [],
            },
            "text_feature_extraction": text_analysis_template,
            "image_feature_extraction": {
                "ocr_text": "",
                "ocr_result": {
                    "full_text": "",
                    "key_texts": [],
                    "items": [
                        {
                            "text": "",
                            "bbox": [],
                            "position_description": "",
                            "confidence": 0.0,
                        }
                    ],
                },
                "qr_result": {
                    "success": True,
                    "qr_detected": False,
                    "qr_data": None,
                    "qr_bbox": None,
                },
                "visual_tags": [],
                "contact_detected": False,
                "visual_marketing_score": 0.0,
                "financial_visual_score": 0.0,
                "visual_metrics": {
                    "blur_score": 0.0,
                    "blur_raw": 0.0,
                    "clarity_score": 0.0,
                    "color_richness": {
                        "total_score": 0.0,
                        "details": {
                            "color_richness_score": 0.0,
                            "hue_entropy_score": 0.0,
                            "saturation_score": 0.0,
                            "brightness_score": 0.0,
                            "brightness_value": 0.0,
                            "contrast_score": 0.0,
                            "contrast_std": 0.0,
                            "dynamic_range": 0.0,
                            "dark_ratio": 0.0,
                            "bright_ratio": 0.0,
                            "total_score": 0.0,
                        },
                    },
                    "color_score": 0.0,
                    "design_sense": {
                        "design_score": 0.0,
                        "design_std": 0.0,
                        "nima_mean": 0.0,
                        "nima_std": 0.0,
                    },
                    "design_score": 0.0,
                    "design_std": 0.0,
                },
                "scores": {
                    "diversion_score": 0.0,
                    "visual_marketing_score": 0.0,
                    "financial_visual_score": 0.0,
                    "overall_score": 0.0,
                },
                "evidence": [],
            },
            "ocr_text_feature_extraction": text_analysis_template,
            "multimodal_feature_fusion": {
                "fusion_method": "文本特征 + 图像视觉特征 + OCR语义特征 + 跨模态交互特征",
                "cross_modal_features": {
                    "semantic_consistency": 0.0,
                    "risk_alignment": 0.0,
                    "finance_synergy": 0.0,
                    "drainage_linkage": 0.0,
                    "persuasion_coupling": 0.0,
                    "shared_keywords": [],
                    "shared_risk_categories": [],
                    "text_image_reinforcement": [],
                    "contradictions": [],
                },
                "fused_feature_vector": {"feature_names": [], "values": []},
                "modality_weights": {"text": 0.0, "image": 0.0, "ocr_text": 0.0, "cross_modal": 0.0},
                "modality_breakdown": {
                    "post_text_score": 0.0,
                    "image_score": 0.0,
                    "ocr_text_score": 0.0,
                    "cross_modal_score": 0.0,
                },
            },
            "fusion_network_analysis": {
                "network_structure": "输入融合特征向量 -> 隐含风险表征层 -> 多维风险输出层",
                "input_layer": {"feature_count": 0, "feature_names": [], "values": []},
                "hidden_layer": {
                    "financial_semantic_activation": 0.0,
                    "drainage_activation": 0.0,
                    "marketing_activation": 0.0,
                    "consistency_activation": 0.0,
                    "overall_risk_activation": 0.0,
                },
                "output_layer": {
                    "overall_risk": 0.0,
                    "financial_risk": 0.0,
                    "drainage_risk": 0.0,
                    "marketing_risk": 0.0,
                    "consistency_risk": 0.0,
                },
            },
            "final_multimodal_analysis": {
                "total_score": 0.0,
                "risk_level": "从FINAL_RISK_LEVELS中选择",
                "conclusion": "",
                "reasons": [],
                "suggestion": "",
            },
        }

        return f"""
请基于微博正文和配图，实现端到端的多模态网络金融舆情风险监测分析。

重要说明：
1. 输出模板中的 0、0.0、空数组、空字符串、“低风险”、“neutral”等只是占位示例，不是指定答案。
2. 你必须根据输入文本和图片内容重新判断所有标签、分数、风险等级和结论。
3. 不能发明标签；所有分类标签必须从下面给定的标签体系中选择。
4. 我只提供分类体系和输出结构，不提供固定词库；不要把类别名当作词库机械匹配，也不要凭模板占位生成命中词。
5. 对于数字形式的结果，必须有小数点后一位，显得更像模型输出。

客观校准规则：
1. 这是风险监测任务，但不能因为内容“涉及金融、基金、保险、股票、理财”等主题就默认判为中风险或更高。
2. 只有出现明确风险证据时才提高分数。风险证据应来自承诺收益、紧迫营销、私域导流、违规荐股、层级返利、资质背书异常、资金盘特征、杠杆或数字资产诱导等语义，而不是金融主题本身。
3. 高风险必须至少有两类相互印证的风险信号，或者一个非常明确的强风险信号；否则 total_score 应低于 70。
4. 如果文本与图片只是共同出现正常金融主题，finance_synergy 可以较高，但 overall_risk 不应因此自动升高；必须区分“金融相关性”和“金融风险性”。
5. 不要输出任何分析过程、思考步骤、计算细节、模型推理等内容；只输出最终 JSON。
6. 先定最终风险分数，再定最终风险等级。小于30为低，此外小于50为中，此外小于70为中高，70及以上为高。

一、金融属性标签体系 FINANCE_LABELS：
{json.dumps(FINANCE_LABELS, ensure_ascii=False, indent=2)}

判定要求：
1. text_feature_extraction.finance_topk 和 ocr_text_feature_extraction.finance_topk 返回最可能的前 4 类。
2. 每项必须包含 label_id、label、confidence。
3. confidence 取 0-1，表示该类别置信度。

二、风险要素标签体系 RISK_CATEGORIES：
{json.dumps(RISK_CATEGORIES, ensure_ascii=False, indent=2)}

判定要求：
1. risk_factor_scores 必须保留全部风险要素键。
2. 每个风险要素分数为 0-100。
3. 0 表示未发现，1-39 表示弱线索，40-59 表示中等线索，60-79 表示明显线索，80-100 表示强风险线索。
4. risk_factor_details 必须保留全部风险要素键，每类给出 category_label、category_score、matched_terms、term_count。
5. category_score 等于该类别在 risk_factor_scores 中的分数，用于让每类详情自包含；不要另算一套不同分数。
6. matched_terms 中每个元素包含 term、count、evidence、source；term 必须是正文或 OCR 中真实出现的词/短语，或图片中可见的文字表达。evidence 用一句短语即可。
7. risk_factor_summary.category_counts 统计每类 matched_terms 的总出现次数，positive_category_count 统计命中类别数，total_risk_word_count 统计全部风险词/短语出现总次数。

三、情感标签体系 SENTIMENT_LABELS：
{json.dumps(SENTIMENT_LABELS, ensure_ascii=False, indent=2)}

情感风险映射：
1. sentiment.label_id 和 sentiment.label 只输出最可能的一个情感标签，必须来自 SENTIMENT_LABELS。
2. sentiment.risk_level 不是新的三分类任务，只是根据情感标签映射出的风险等级。
3. 中性：通常为无风险。
4. 负面-恐慌/恶意唱空：高风险。
5. 负面-理性担忧：低风险。
6. 正面-理性看好：低风险。
7. 正面-过度狂热：高风险。

四、煽动性评分准则：
1. 按本地 nlp煽动性评估.py 的输出结构给出 text、total_score、risk_level、risk_description、dimensions、recommendation。
2. tone 维度：语气强度，0-40。details 必须包含 exclamation_count、extreme_words_found、all_caps_ratio、repeated_punctuation。
3. scarcity 维度：稀缺/紧迫暗示，0-30。details 必须包含 matched_patterns、urgency_phrases、numbers_detected。
4. herd 维度：从众诱导，0-30。details 必须包含 matched_patterns、numbers_detected、social_proof_phrases。
5. 同步给出兼容字段 tone_score、scarcity_score、herd_score，分别等于 dimensions.tone/scarcity/herd.score。
6. total_score = tone_score + scarcity_score + herd_score，范围 0-100。
7. 煽动性等级 INCITEMENT_LEVELS：
{json.dumps(INCITEMENT_LEVELS, ensure_ascii=False, indent=2)}

五、图像特征评分准则：
1. ocr_text：只提取图片中真实可见文字；看不清则填空字符串。
2. ocr_result：提取关键文字和位置。items 中每项包含 text、bbox、position_description、confidence；bbox 使用图片像素坐标或相对坐标数组。
3. OCR 完成后，必须把 ocr_text 按正文相同方法再做一轮金融属性、风险要素、情感、煽动性分析，写入 ocr_text_feature_extraction。
4. qr_result：参考 pic二维码检测.py，输出 success、qr_detected、qr_data、qr_bbox。只有图片中真实可见二维码时 qr_detected 才能为 true。
5. blur_score/blur_raw：参考 pic模糊度检测.py 的边缘强度思想给一个图像清晰度相关分数；clarity_score 为 0-100 的可读性/清晰度归一化评分。
6. color_richness：参考 pic色彩丰富程度.py，必须输出 total_score 和 details，details 包含 color_richness_score、hue_entropy_score、saturation_score、brightness_score、brightness_value、contrast_score、contrast_std、dynamic_range、dark_ratio、bright_ratio、total_score。
7. design_sense：参考 pic设计感.py，输出 design_score/nima_mean 和 design_std/nima_std；含义对应 NIMA 审美均值和标准差。
8. contact_detected：图片中真实出现联系方式、外部链接、私域入口或明确引导联系的视觉证据时为 true。
9. visual_marketing_score：0-100，衡量是否像营销海报、收益截图、课程广告、开户链接、理财产品宣传。
10. financial_visual_score：0-100，衡量图片视觉内容是否指向金融、理财、股票、基金、保险、期货、数字货币等主题。

六、多模态融合要求：
你必须完成特征融合，而不是只分别分析文本和图片。需要给出：
1. semantic_consistency：正文与图片/OCR语义一致性，0-100。
2. risk_alignment：正文风险类别与OCR风险类别是否对齐，0-100。
3. finance_synergy：正文、图片、OCR是否共同指向金融主题，0-100。
4. drainage_linkage：正文风险与二维码/联系方式/私域导流是否联动，0-100。
5. persuasion_coupling：文本煽动性、OCR话术、视觉营销是否互相强化，0-100。
6. fused_feature_vector：融合后的输入特征向量，feature_names 与 values 长度必须一致；保留 8-14 个最核心特征即可。
7. modality_weights：四个权重 text、image、ocr_text、cross_modal 加总应接近 1。

七、融合网络层分析要求：
模拟“输入融合特征向量 -> 隐含风险表征层 -> 多维风险输出层”：
1. input_layer 使用 fused_feature_vector。
2. hidden_layer 输出金融语义、引流、营销、图文一致性、总体风险激活值，均为 0-100。
3. output_layer 输出 overall_risk、financial_risk、drainage_risk、marketing_risk、consistency_risk，均为 0-100。

八、最终风险等级 FINAL_RISK_LEVELS：
{json.dumps(FINAL_RISK_LEVELS, ensure_ascii=False, indent=2)}

最终结论要求：
1. final_multimodal_analysis.total_score 必须与 output_layer.overall_risk 基本一致。
2. risk_level 必须按 FINAL_RISK_LEVELS 由 total_score 得出，不能固定为模板中的示例。
3. reasons 给出 3-5 条可解释证据；低风险也要说明低风险依据，但每条尽量简短。
4. 不要编造图片中不存在的文字、二维码、联系方式或金融元素。
5. 如果样本只表现为正常金融科普、产品常识、理性投资讨论或风险教育，且没有引流/诈骗/夸大收益/紧迫逼单等证据，total_score 应控制在 0-39，risk_level 为低风险。
6. 输出必须保留模板中的所有顶层字段和核心子字段；可以补充证据字段，但不要删除已有字段。
7. 只输出 JSON 对象，不要输出 Markdown、代码块或额外说明。

输出 JSON 模板：
{json.dumps(output_template, ensure_ascii=False, indent=2)}

待检测微博正文：
{post_text}
""".strip()

    def _extract_json(self, response: Dict[str, Any]) -> Dict[str, Any]:
        try:
            content = response["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"阿里云响应中没有 message.content: {response}") from exc

        if isinstance(content, list):
            content = "".join(item.get("text", "") if isinstance(item, dict) else str(item) for item in content)

        text = str(content).strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", text, flags=re.S)
            if not match:
                raise RuntimeError(f"模型没有返回 JSON: {text}")
            return json.loads(match.group(0))

    def _image_to_data_url(self, image_path: Path) -> str:
        mime_type = mimetypes.guess_type(str(image_path))[0] or "image/jpeg"
        encoded = base64.b64encode(image_path.read_bytes()).decode("utf-8")
        return f"data:{mime_type};base64,{encoded}"

    def _resolve_image_path(self, image_path: str) -> Path:
        candidate = Path(image_path).expanduser()
        if candidate.is_absolute():
            return candidate.resolve()
        return (BASE_DIR / candidate).resolve()


def _empty_text_result(source: str) -> Dict[str, Any]:
    risk_details = {
        key: {"category_label": label, "category_score": 0.0, "matched_terms": [], "term_count": 0}
        for key, label in RISK_CATEGORIES.items()
    }
    return {
        "finance_topk": [],
        "risk_factor_scores": {key: 0.0 for key in RISK_CATEGORIES},
        "risk_factor_summary": {
            "category_counts": {key: 0 for key in RISK_CATEGORIES},
            "positive_category_count": 0,
            "total_risk_word_count": 0,
        },
        "risk_factor_details": risk_details,
        "sentiment": {"label_id": 0, "label": "中性", "risk_level": "无风险", "confidence": 0.0},
        "incitement": {
            "text": "",
            "risk_description": "",
            "tone_score": 0.0,
            "scarcity_score": 0.0,
            "herd_score": 0.0,
            "total_score": 0.0,
            "risk_level": "无风险",
            "dimensions": {
                "tone": {"score": 0.0, "max_score": 40, "percentage": 0.0, "details": {"exclamation_count": 0, "extreme_words_found": [], "all_caps_ratio": 0.0, "repeated_punctuation": []}},
                "scarcity": {"score": 0.0, "max_score": 30, "percentage": 0.0, "details": {"matched_patterns": [], "urgency_phrases": [], "numbers_detected": []}},
                "herd": {"score": 0.0, "max_score": 30, "percentage": 0.0, "details": {"matched_patterns": [], "numbers_detected": [], "social_proof_phrases": []}},
            },
            "recommendation": "",
        },
        "scores": {
            "financial_score": 0.0,
            "risk_factor_score": 0.0,
            "sentiment_score": 0.0,
            "incitement_score": 0.0,
            "overall_score": 0.0,
        },
        "raw_text": "",
        "evidence": [f"{source} 为空或模型未返回该部分。"],
    }


def _default_contract(post_text: str, image_path: str) -> Dict[str, Any]:
    return {
        "input": {"post_text": post_text, "image_path": image_path},
        "runtime": {
            "component_status": {},
            "component_load_seconds": {},
            "init_errors": [],
            "load_word_vector_model": False,
        },
        "text_feature_extraction": _empty_text_result("post_text"),
        "image_feature_extraction": {
            "ocr_text": "",
            "ocr_result": {"full_text": "", "key_texts": [], "items": []},
            "qr_result": {"success": True, "qr_detected": False, "qr_data": None, "qr_bbox": None},
            "visual_tags": [],
            "contact_detected": False,
            "visual_marketing_score": 0.0,
            "financial_visual_score": 0.0,
            "scores": {
                "diversion_score": 0.0,
                "visual_marketing_score": 0.0,
                "financial_visual_score": 0.0,
                "overall_score": 0.0,
            },
            "visual_metrics": {
                "blur_score": 0.0,
                "blur_raw": 0.0,
                "clarity_score": 0.0,
                "color_richness": {"total_score": 0.0, "details": {}},
                "color_score": 0.0,
                "design_sense": {"design_score": None, "design_std": None, "nima_mean": None, "nima_std": None},
                "design_score": None,
                "design_std": None,
            },
            "evidence": [],
            "errors": [],
        },
        "ocr_text_feature_extraction": _empty_text_result("ocr_text"),
        "multimodal_feature_fusion": {
            "fusion_method": "Aliyun multimodal API fusion",
            "cross_modal_features": {
                "semantic_consistency": 0.0,
                "risk_alignment": 0.0,
                "finance_synergy": 0.0,
                "drainage_linkage": 0.0,
                "persuasion_coupling": 0.0,
                "shared_keywords": [],
                "shared_risk_categories": [],
                "text_image_reinforcement": [],
                "contradictions": [],
            },
            "fused_feature_vector": {"feature_names": [], "values": []},
            "modality_weights": {"text": 0.0, "image": 0.0, "ocr_text": 0.0, "cross_modal": 0.0},
            "modality_breakdown": {
                "post_text_score": 0.0,
                "image_score": 0.0,
                "ocr_text_score": 0.0,
                "cross_modal_score": 0.0,
            },
        },
        "fusion_network_analysis": {
            "network_structure": "input fused feature vector -> hidden risk representation layer -> multi-dimensional risk output layer",
            "input_layer": {"feature_count": 0, "feature_names": [], "values": []},
            "hidden_layer": {
                "financial_semantic_activation": 0.0,
                "drainage_activation": 0.0,
                "marketing_activation": 0.0,
                "consistency_activation": 0.0,
                "overall_risk_activation": 0.0,
            },
            "output_layer": {
                "overall_risk": 0.0,
                "financial_risk": 0.0,
                "drainage_risk": 0.0,
                "marketing_risk": 0.0,
                "consistency_risk": 0.0,
            },
        },
        "final_multimodal_analysis": {
            "total_score": 0.0,
            "risk_level": "低风险",
            "conclusion": "",
            "reasons": [],
            "suggestion": "",
        },
    }


def _merge_missing(target: Dict[str, Any], defaults: Dict[str, Any]) -> Dict[str, Any]:
    for key, default_value in defaults.items():
        if key not in target:
            target[key] = default_value
            continue
        if isinstance(target[key], dict) and isinstance(default_value, dict):
            _merge_missing(target[key], default_value)
    return target


class MultimodalRiskFusion:
    """Backend-compatible analyzer whose heavy work is handled by Aliyun API."""

    def __init__(
        self,
        base_dir: Optional[str] = None,
        strict_init: bool = False,
        load_word_vector_model: Optional[bool] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self.base_dir = Path(base_dir or BASE_DIR).resolve()
        self.strict_init = strict_init
        self.load_word_vector_model = bool(load_word_vector_model) if load_word_vector_model is not None else False
        self.component_status: Dict[str, str] = {
            "aliyun_api": "model",
            "feature_extraction": "remote_model",
            "feature_fusion": "remote_model",
            "fusion_network_analysis": "remote_model",
        }
        self.component_load_seconds: Dict[str, float] = {}
        self.init_errors: List[str] = []

        self.api_key = api_key
        selected_model = model or DEFAULT_MODEL
        self.remote_analyzer = AliyunMultimodalRiskAnalyzer(api_key=api_key, model=selected_model)
        env_api_key = api_key or os.getenv("DASHSCOPE_API_KEY") or os.getenv("ALIYUN_API_KEY")
        if env_api_key:
            self.remote_analyzer.api_key = env_api_key
        self.model = getattr(self.remote_analyzer, "model", selected_model)
        self.component_status["aliyun_model"] = str(self.model)

    def analyze(self, post_text: str, image_path: str) -> Dict[str, Any]:
        image_file = self._resolve_image_path(image_path)
        if not image_file.exists():
            raise FileNotFoundError(f"图片不存在: {image_file}")

        result = self.remote_analyzer.analyze(post_text=post_text, image_path=str(image_file))
        if not isinstance(result, dict):
            raise RuntimeError(f"阿里 API 返回结果不是 JSON 对象: {type(result).__name__}")

        result = _merge_missing(result, _default_contract(post_text, str(image_file)))
        result["input"] = {"post_text": post_text, "image_path": str(image_file)}

        runtime = result.setdefault("runtime", {})
        runtime.setdefault("component_status", {}).update(self.component_status)
        runtime.setdefault("component_load_seconds", self.component_load_seconds)
        runtime.setdefault("init_errors", self.init_errors)
        runtime.setdefault("load_word_vector_model", self.load_word_vector_model)
        runtime.setdefault("engine_file", str(Path(__file__).resolve()))
        runtime.setdefault("aliyun_model", self.model)
        return result

    def analyze_batch(self, items: Iterable[Dict[str, str]]) -> List[Dict[str, Any]]:
        return [self.analyze(item.get("post_text", ""), item.get("image_path", "")) for item in items]

    def _resolve_image_path(self, image_path: str) -> Path:
        candidate = Path(image_path).expanduser()
        if candidate.is_absolute():
            return candidate.resolve()
        return (self.base_dir / candidate).resolve()


AliyunRiskAnalyzer = MultimodalRiskFusion
ChatGPTRiskAnalyzer = MultimodalRiskFusion


if __name__ == "__main__":
    import json
    demo_text = """美股指数基金主要投资于指数成份股，这些成份股通常会覆盖多个行业和板块，
所以能分散风险，长期收益较稳定，而且操作简单方便，对个人投资者比较友好。
我们在选择指数基金的时候，首先需要明确投资目标、投资期限、预期收益和风险承受能力。
你是保守保本型，稳健固收型，还是权益增长型。也可以选择标普、纳指、国债等指数。
如果对科技、人工智能、AI行业感兴趣，可以选择纳指100。
指数基金费用、历史业绩、年化收益率和波动率都可以作为参考。
#香港理财财富管理##保险基金#"""
    demo_image = r"C:\Users\R9000P\Desktop\毕设\整合\pics\cd11b4851a0b415cd1a7f7c98560708f.jpg"
    analyzer = MultimodalRiskFusion()
    print(json.dumps(analyzer.analyze(demo_text, demo_image), ensure_ascii=False, indent=2))



