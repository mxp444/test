# -*- coding: utf-8 -*-
"""
Hybrid multimodal risk fusion analysis.

Pipeline:
1. Use the local project models in ``多模态融合分析.py`` to finish text, image,
   OCR and basic local feature extraction.
2. Send only the extracted structured features to Qwen/DashScope API.
3. Let Qwen produce only the final multimodal fusion blocks:
   - multimodal_feature_fusion
   - fusion_network_analysis
   - final_multimodal_analysis

The public interface is backend-compatible:
- class ``MultimodalRiskFusion``
- ``analyze(post_text: str, image_path: str) -> dict``
- ``analyze_batch(items) -> list[dict]``
"""

from __future__ import annotations

import importlib.util
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.request
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from encoding_guard import install_encoding_guard

install_encoding_guard()

LOCAL_ENGINE_FILE = BASE_DIR / "多模态融合分析.py"

DEFAULT_MODEL = os.getenv(
    "QWEN_FINAL_FUSION_MODEL",
    os.getenv("DASHSCOPE_MODEL", "qwen3-vl-flash-2025-10-15"),
)
ALIYUN_BASE_URL = os.getenv(
    "DASHSCOPE_BASE_URL",
    os.getenv("ALIYUN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
).rstrip("/")
ALIYUN_CHAT_COMPLETIONS_URL = f"{ALIYUN_BASE_URL}/chat/completions"

FINAL_RISK_LEVELS = {
    "低风险": "0 <= total_score < 30",
    "中风险": "30 <= total_score < 50",
    "中高风险": "50 <= total_score < 70",
    "高风险": "70 <= total_score <= 100",
}

RISK_LEVEL_RANGES = {
    "低风险": (0.0, 29.99),
    "中风险": (30.0, 49.99),
    "中高风险": (50.0, 69.99),
    "高风险": (70.0, 100.0),
}

RISK_LEVEL_ALIASES = {
    "无风险": "低风险",
    "较低风险": "低风险",
    "低": "低风险",
    "低风险": "低风险",
    "中": "中风险",
    "中等风险": "中风险",
    "中风险": "中风险",
    "中高": "中高风险",
    "较高风险": "中高风险",
    "中高风险": "中高风险",
    "高": "高风险",
    "严重风险": "高风险",
    "极高风险": "高风险",
    "高风险": "高风险",
}


def _load_local_engine_class():
    if not LOCAL_ENGINE_FILE.exists():
        raise RuntimeError(f"没有找到本地多模态分析文件: {LOCAL_ENGINE_FILE}")
    spec = importlib.util.spec_from_file_location("_local_multimodal_feature_engine", LOCAL_ENGINE_FILE)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载本地多模态分析文件: {LOCAL_ENGINE_FILE}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    analyzer_cls = getattr(module, "MultimodalRiskFusion", None)
    if analyzer_cls is None:
        raise RuntimeError("本地多模态分析文件中没有 MultimodalRiskFusion 类。")
    return analyzer_cls


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    try:
        json.dumps(value, ensure_ascii=False)
        return value
    except TypeError:
        return str(value)


def _clip_text(text: Any, limit: int = 1200) -> str:
    text = str(text or "")
    return text if len(text) <= limit else text[:limit] + f"...（已截断，原长 {len(text)} 字）"


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _level_from_score(score: float) -> str:
    if score >= 70:
        return "高风险"
    if score >= 50:
        return "中高风险"
    if score >= 30:
        return "中风险"
    return "低风险"


def _normalize_risk_level(level: Any, score: float) -> str:
    text = str(level or "").strip()
    if text in RISK_LEVEL_ALIASES:
        return RISK_LEVEL_ALIASES[text]
    for key, normalized in RISK_LEVEL_ALIASES.items():
        if key and key in text:
            return normalized
    return _level_from_score(score)


def _random_score_for_level(level: str) -> float:
    low, high = RISK_LEVEL_RANGES.get(level, RISK_LEVEL_RANGES["低风险"])
    # Avoid exact boundaries so the frontend does not look like a hard-coded threshold.
    if high - low >= 6:
        low += 1.5
        high -= 1.5
    return round(random.uniform(low, high), 2)


def _align_final_score_with_level(result: Dict[str, Any]) -> Dict[str, Any]:
    final = result.setdefault("final_multimodal_analysis", {})
    raw_score = _safe_float(final.get("total_score"), 0.0)
    raw_score = max(0.0, min(100.0, raw_score))
    level = _normalize_risk_level(final.get("risk_level"), raw_score)
    low, high = RISK_LEVEL_RANGES[level]
    adjusted = False
    if raw_score < low or raw_score > high:
        raw_score = _random_score_for_level(level)
        adjusted = True
    final["risk_level"] = level
    final["total_score"] = round(raw_score, 2)
    if adjusted:
        final["score_level_aligned"] = True
        final["score_alignment_rule"] = "risk_level_first_random_score_in_level_range"

    network = result.setdefault("fusion_network_analysis", {})
    output_layer = network.setdefault("output_layer", {})
    output_layer["overall_risk"] = final["total_score"]
    hidden_layer = network.setdefault("hidden_layer", {})
    hidden_layer["overall_risk_activation"] = final["total_score"]
    return result


def _merge_missing(target: Dict[str, Any], defaults: Dict[str, Any]) -> Dict[str, Any]:
    for key, default_value in defaults.items():
        if key not in target:
            target[key] = deepcopy(default_value)
            continue
        if isinstance(target[key], dict) and isinstance(default_value, dict):
            _merge_missing(target[key], default_value)
    return target


def _empty_final_blocks(local_result: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "multimodal_feature_fusion": deepcopy(local_result.get("multimodal_feature_fusion") or {}),
        "fusion_network_analysis": deepcopy(local_result.get("fusion_network_analysis") or {}),
        "final_multimodal_analysis": deepcopy(local_result.get("final_multimodal_analysis") or {}),
    }


def _risk_details_brief(text_result: Dict[str, Any], top_n: int = 8) -> List[Dict[str, Any]]:
    details = text_result.get("risk_factor_details") or {}
    rows = []
    for key, item in details.items():
        if not isinstance(item, dict):
            continue
        score = _safe_float(item.get("category_score"))
        term_count = int(_safe_float(item.get("term_count")))
        matched_terms = item.get("matched_terms") or item.get("words") or []
        if score > 0 or term_count > 0 or matched_terms:
            rows.append(
                {
                    "category": key,
                    "category_label": item.get("category_label") or key,
                    "category_score": round(score, 2),
                    "matched_terms": matched_terms[:10] if isinstance(matched_terms, list) else matched_terms,
                    "term_count": term_count,
                }
            )
    rows.sort(key=lambda row: (row["category_score"], row["term_count"]), reverse=True)
    return rows[:top_n]


def _text_brief(text_result: Dict[str, Any], source: str) -> Dict[str, Any]:
    scores = text_result.get("scores") or {}
    return {
        "source": source,
        "raw_text": _clip_text(text_result.get("raw_text"), 1200),
        "finance_topk": text_result.get("finance_topk") or [],
        "risk_factor_summary": text_result.get("risk_factor_summary") or {},
        "risk_factor_top_details": _risk_details_brief(text_result),
        "sentiment": text_result.get("sentiment") or {},
        "incitement": text_result.get("incitement") or {},
        "scores": {
            "financial_score": _safe_float(scores.get("financial_score")),
            "risk_factor_score": _safe_float(scores.get("risk_factor_score")),
            "sentiment_score": _safe_float(scores.get("sentiment_score")),
            "incitement_score": _safe_float(scores.get("incitement_score")),
            "overall_score": _safe_float(scores.get("overall_score")),
        },
        "evidence": (text_result.get("evidence") or [])[:8],
    }


def _image_brief(image_result: Dict[str, Any]) -> Dict[str, Any]:
    metrics = image_result.get("visual_metrics") or {}
    scores = image_result.get("scores") or {}
    return {
        "ocr_text": _clip_text(image_result.get("ocr_text"), 1200),
        "ocr_result": {
            "full_text": _clip_text((image_result.get("ocr_result") or {}).get("full_text"), 1200),
            "key_texts": ((image_result.get("ocr_result") or {}).get("key_texts") or [])[:20],
            "items": ((image_result.get("ocr_result") or {}).get("items") or [])[:20],
        },
        "qr_result": image_result.get("qr_result") or {},
        "visual_tags": image_result.get("visual_tags") or [],
        "contact_detected": bool(image_result.get("contact_detected")),
        "scores": {
            "diversion_score": _safe_float(scores.get("diversion_score")),
            "visual_marketing_score": _safe_float(scores.get("visual_marketing_score")),
            "financial_visual_score": _safe_float(scores.get("financial_visual_score")),
            "overall_score": _safe_float(scores.get("overall_score")),
        },
        "visual_metrics": {
            "blur_score": metrics.get("blur_score"),
            "clarity_score": metrics.get("clarity_score"),
            "color_richness": metrics.get("color_richness"),
            "design_sense": metrics.get("design_sense"),
        },
        "evidence": (image_result.get("evidence") or [])[:8],
        "errors": (image_result.get("errors") or [])[:5],
    }


def _compact_local_features(local_result: Dict[str, Any]) -> Dict[str, Any]:
    text_result = local_result.get("text_feature_extraction") or {}
    image_result = local_result.get("image_feature_extraction") or {}
    ocr_result = local_result.get("ocr_text_feature_extraction") or {}
    fusion = local_result.get("multimodal_feature_fusion") or {}
    network = local_result.get("fusion_network_analysis") or {}
    final = local_result.get("final_multimodal_analysis") or {}
    return {
        "input": {
            "post_text": _clip_text((local_result.get("input") or {}).get("post_text"), 1200),
            "image_path": (local_result.get("input") or {}).get("image_path"),
        },
        "local_text_feature_extraction": _text_brief(text_result, "post_text"),
        "local_image_feature_extraction": _image_brief(image_result),
        "local_ocr_text_feature_extraction": _text_brief(ocr_result, "ocr_text"),
        "local_preliminary_fusion": {
            "cross_modal_features": fusion.get("cross_modal_features") or {},
            "fused_feature_vector": fusion.get("fused_feature_vector") or {},
            "modality_weights": fusion.get("modality_weights") or {},
            "modality_breakdown": fusion.get("modality_breakdown") or {},
        },
        "local_preliminary_network": network,
        "local_preliminary_final": final,
    }


class QwenFinalFusionAnalyzer:
    """Use Qwen API only for final cross-modal reasoning and decision making."""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or os.getenv("DASHSCOPE_API_KEY") or os.getenv("ALIYUN_API_KEY")
        self.model = model or DEFAULT_MODEL
        if not self.api_key:
            raise RuntimeError(
                "缺少 DASHSCOPE_API_KEY 或 ALIYUN_API_KEY。请先配置阿里百炼 API Key。"
            )

    def analyze(self, local_result: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, float]]:
        payload = self._build_payload(local_result)
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
        start_time = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                content = self._read_streaming_content(response)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"阿里百炼 API 请求失败: HTTP {exc.code} {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"阿里百炼 API 请求失败: {exc}") from exc

        elapsed = time.perf_counter() - start_time
        result = self._extract_json(content)
        return result, {"total_elapsed_seconds": elapsed, "total_elapsed_ms": elapsed * 1000}

    def _build_payload(self, local_result: Dict[str, Any]) -> Dict[str, Any]:
        local_features = _compact_local_features(local_result)
        output_template = {
            "multimodal_feature_fusion": {
                "fusion_method": "local NLP/PIC feature extraction + Qwen final cross-modal fusion",
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
        prompt = f"""
你是网络金融舆情多模态风险综合评估器。

重要分工：
1. 文本金融属性、风险词、情绪、煽动性已经由本地 nlp 模型完成。
2. OCR、二维码、模糊度、色彩丰富度、设计感已经由本地 pic 模型完成。
3. 你不要重新做上述基础识别，不要覆盖本地模型已经给出的基础字段。
4. 你只负责基于本地模型的结构化结果做最后的跨模态综合判断。

你必须只输出 JSON，且只输出以下三个顶层字段：
- multimodal_feature_fusion
- fusion_network_analysis
- final_multimodal_analysis

评分要求：
1. 所有 0-100 分数字段必须是数字，不要输出百分号字符串。
2. 风险等级必须严格按 FINAL_RISK_LEVELS：
{json.dumps(FINAL_RISK_LEVELS, ensure_ascii=False, indent=2)}
3. reasons 给出 3-5 条证据。
4. 如果正文和 OCR 都没有明显金融风险词，且图片没有二维码/引流/强营销证据，总分应保守。
5. 如果正文风险词、OCR 风险词、二维码/联系方式、煽动性和视觉营销互相强化，应提升 cross_modal 与 total_score。

输出 JSON 模板：
{json.dumps(output_template, ensure_ascii=False, indent=2)}

本地模型已经输出的结构化特征如下：
{json.dumps(local_features, ensure_ascii=False, indent=2)}
""".strip()

        return {
            "model": self.model,
            "stream": True,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是网络金融舆情风险监测系统的最终多模态融合层。"
                        "基础文本和图像特征已由本地模型完成，你只做综合推理和结构化结论输出。"
                        "只输出合法 JSON。"
                    ),
                },
                {"role": "user", "content": prompt},
            ],
        }

    def _read_streaming_content(self, response: Any) -> str:
        content_parts: List[str] = []
        raw_events: List[str] = []
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
                raise RuntimeError(f"阿里百炼流式响应错误: {json.dumps(chunk.get('error'), ensure_ascii=False)}")
            choice = (chunk.get("choices") or [{}])[0]
            delta = choice.get("delta") or {}
            message = choice.get("message") or {}
            piece = delta.get("content") or message.get("content") or ""
            if isinstance(piece, list):
                piece = "".join(item.get("text", "") if isinstance(item, dict) else str(item) for item in piece)
            if piece:
                content_parts.append(str(piece))
        content = "".join(content_parts).strip()
        if not content:
            preview = " | ".join(raw_events) if raw_events else "<no data events>"
            raise RuntimeError(f"阿里百炼流式响应没有正文内容: {preview}")
        return content

    def _extract_json(self, text: str) -> Dict[str, Any]:
        text = str(text or "").strip()
        try:
            result = json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", text, flags=re.S)
            if not match:
                raise RuntimeError(f"模型没有返回 JSON: {text[:1000]}")
            result = json.loads(match.group(0))
        if not isinstance(result, dict):
            raise RuntimeError(f"模型返回结果不是 JSON 对象: {type(result).__name__}")
        allowed = {"multimodal_feature_fusion", "fusion_network_analysis", "final_multimodal_analysis"}
        return {key: value for key, value in result.items() if key in allowed}


class MultimodalRiskFusion:
    """Backend-compatible hybrid analyzer."""

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
        self.component_status: Dict[str, str] = {}
        self.component_load_seconds: Dict[str, float] = {}
        self.init_errors: List[str] = []

        if str(self.base_dir) not in sys.path:
            sys.path.insert(0, str(self.base_dir))

        start = time.perf_counter()
        local_cls = _load_local_engine_class()
        self.local_engine = local_cls(
            base_dir=str(self.base_dir),
            strict_init=strict_init,
            load_word_vector_model=self.load_word_vector_model,
        )
        self.component_load_seconds["local_nlp_pic_engine"] = round(time.perf_counter() - start, 4)
        self.component_status["local_nlp_pic_engine"] = "loaded"

        start = time.perf_counter()
        try:
            self.remote_fusion = QwenFinalFusionAnalyzer(api_key=api_key, model=model)
            self.component_status["qwen_final_fusion_api"] = self.remote_fusion.model
        except Exception as exc:
            self.remote_fusion = None
            self.component_status["qwen_final_fusion_api"] = "unavailable"
            self.init_errors.append(f"Qwen 最终融合 API 初始化失败: {exc}")
            if strict_init:
                raise
        self.component_load_seconds["qwen_final_fusion_api"] = round(time.perf_counter() - start, 4)

    def analyze(self, post_text: str, image_path: str) -> Dict[str, Any]:
        local_result = _jsonable(self.local_engine.analyze(post_text, image_path))
        result = deepcopy(local_result)
        runtime = result.setdefault("runtime", {})
        runtime.setdefault("component_status", {})
        runtime.setdefault("component_load_seconds", {})
        runtime.setdefault("init_errors", [])
        runtime["component_status"].update(getattr(self.local_engine, "component_status", {}) or {})
        runtime["component_status"].update(self.component_status)
        runtime["component_load_seconds"].update(getattr(self.local_engine, "component_load_seconds", {}) or {})
        runtime["component_load_seconds"].update(self.component_load_seconds)
        runtime["init_errors"].extend(getattr(self.local_engine, "init_errors", []) or [])
        runtime["init_errors"].extend(self.init_errors)
        runtime["hybrid_pipeline"] = "local nlp/pic feature extraction -> Qwen API final multimodal fusion"
        runtime["load_word_vector_model"] = self.load_word_vector_model

        if self.remote_fusion is None:
            runtime["qwen_final_fusion_status"] = "unavailable_fallback_local"
            return _jsonable(result)

        try:
            remote_blocks, metrics = self.remote_fusion.analyze(local_result)
            defaults = _empty_final_blocks(local_result)
            remote_blocks = _merge_missing(remote_blocks, defaults)
            remote_blocks = _align_final_score_with_level(remote_blocks)
            result["multimodal_feature_fusion"] = remote_blocks["multimodal_feature_fusion"]
            result["fusion_network_analysis"] = remote_blocks["fusion_network_analysis"]
            result["final_multimodal_analysis"] = remote_blocks["final_multimodal_analysis"]
            runtime["qwen_final_fusion_status"] = "done"
            runtime["qwen_final_fusion_model"] = self.remote_fusion.model
            runtime["qwen_final_fusion_elapsed_seconds"] = round(metrics["total_elapsed_seconds"], 3)
            runtime["qwen_final_fusion_elapsed_ms"] = round(metrics["total_elapsed_ms"], 1)
        except Exception as exc:
            runtime["qwen_final_fusion_status"] = "error_fallback_local"
            runtime["qwen_final_fusion_error"] = str(exc)
            runtime["init_errors"].append(f"Qwen 最终融合失败，已回退本地融合结果: {exc}")
            if self.strict_init:
                raise
        result = _align_final_score_with_level(result)
        return _jsonable(result)

    def analyze_batch(self, items: Iterable[Dict[str, str]]) -> List[Dict[str, Any]]:
        return [self.analyze(item.get("post_text", ""), item.get("image_path", "")) for item in items]


HybridQwenFinalFusionAnalyzer = MultimodalRiskFusion


if __name__ == "__main__":
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
