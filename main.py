import base64
import json
import mimetypes
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


DEFAULT_MODEL = os.getenv("DASHSCOPE_MODEL", os.getenv("ALIYUN_MODEL", "qwen-vl-plus"))
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
    "低风险": "0 <= total_score < 40",
    "中风险": "40 <= total_score < 60",
    "中高风险": "60 <= total_score < 80",
    "高风险": "80 <= total_score <= 100",
}


class AliyunMultimodalRiskAnalyzer:
    """Ask Qwen-VL to complete feature extraction, fusion, network-layer analysis, and final judgment."""

    def __init__(self, api_key: Optional[str] = None, model: str = DEFAULT_MODEL):
        self.api_key = "sk-c628b6ed3d5f45b6b30a3f1ba13431da"
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

        response, aliyun_elapsed_seconds = self._post_chat_completion(post_text=post_text, image_path=image_file)
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
        runtime["aliyun_remote_elapsed_seconds"] = round(aliyun_elapsed_seconds, 3)
        return result

    def _post_chat_completion(self, post_text: str, image_path: Path) -> Tuple[Dict[str, Any], float]:
        request = urllib.request.Request(
            ALIYUN_CHAT_COMPLETIONS_URL,
            data=json.dumps(self._build_payload(post_text, image_path), ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            start_time = time.perf_counter()
            with urllib.request.urlopen(request, timeout=120) as response:
                response_body = response.read()
            elapsed_seconds = time.perf_counter() - start_time
            return json.loads(response_body.decode("utf-8")), elapsed_seconds
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"阿里云百炼 API 请求失败: HTTP {exc.code} {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"阿里云百炼 API 请求失败: {exc}") from exc

    def _build_payload(self, post_text: str, image_path: Path) -> Dict[str, Any]:
        return {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是多模态网络金融舆情风险监测算法。你必须在用户给定的标签体系和评分准则内，"
                        "完成特征提取、特征融合、融合网络层分析和最终风险判断。只输出合法 JSON。"
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
            "temperature": 0.1,
            "max_tokens": 4096,
        }

    def _build_prompt(self, post_text: str) -> str:
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
            "text_feature_extraction": {
                "finance_topk": [{"label_id": 0, "label": "从FINANCE_LABELS中选择", "confidence": 0.0}],
                "risk_factor_scores": {key: 0.0 for key in RISK_CATEGORIES},
                "sentiment": {
                    "label_id": 0,
                    "label": "从SENTIMENT_LABELS中选择",
                    "risk_level": "无风险/低风险/高风险",
                    "confidence": 0.0,
                },
                "incitement": {
                    "tone_score": 0.0,
                    "scarcity_score": 0.0,
                    "herd_score": 0.0,
                    "total_score": 0.0,
                    "risk_level": "从INCITEMENT_LEVELS中选择",
                },
                "scores": {
                    "financial_score": 0.0,
                    "risk_factor_score": 0.0,
                    "sentiment_score": 0.0,
                    "incitement_score": 0.0,
                    "overall_score": 0.0,
                },
                "evidence": [],
            },
            "image_feature_extraction": {
                "ocr_text": "",
                "qr_result": {"qr_detected": False, "qr_data": None, "qr_bbox": None},
                "visual_tags": [],
                "contact_detected": False,
                "visual_marketing_score": 0.0,
                "financial_visual_score": 0.0,
                "evidence": [],
            },
            "ocr_text_feature_extraction": {
                "finance_topk": [{"label_id": 0, "label": "从FINANCE_LABELS中选择", "confidence": 0.0}],
                "risk_factor_scores": {key: 0.0 for key in RISK_CATEGORIES},
                "sentiment": {
                    "label_id": 0,
                    "label": "从SENTIMENT_LABELS中选择",
                    "risk_level": "无风险/低风险/高风险",
                    "confidence": 0.0,
                },
                "incitement": {
                    "tone_score": 0.0,
                    "scarcity_score": 0.0,
                    "herd_score": 0.0,
                    "total_score": 0.0,
                    "risk_level": "从INCITEMENT_LEVELS中选择",
                },
                "scores": {
                    "financial_score": 0.0,
                    "risk_factor_score": 0.0,
                    "sentiment_score": 0.0,
                    "incitement_score": 0.0,
                    "overall_score": 0.0,
                },
                "evidence": [],
            },
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

客观校准规则：
1. 这是风险监测任务，但不能因为内容“涉及金融、基金、保险、股票、理财”等主题就默认判为中风险或更高。
2. 正常金融知识科普、理性投资经验分享、风险提示、产品常识解释、指数基金/定投/保险等中性讨论，如果没有明确诱导、欺诈、引流或夸大承诺证据，应判为低风险。
3. “长期收益较稳定、分散风险、费用、历史业绩、波动率、风险承受能力”等理性表述，属于正常投资教育线索，不能单独作为高风险证据。
4. 只有出现明确风险证据时才提高分数，例如：保本保息/稳赚不赔/高额固定收益承诺、限时逼单、扫码加群/私信/微信/电话导流、内幕荐股、拉下线返利、虚假资质背书、资金盘、杠杆配资、数字货币骗局等。
5. 证据不足时采用保守低估原则：宁可给低风险并说明“金融相关但未见违规诱导证据”，不要为了预警而过度升档。
6. 中风险及以上必须至少有两类相互印证的风险信号，或者一个非常明确的强风险信号；否则 total_score 应低于 40。
7. 如果文本与图片只是共同出现正常金融主题，finance_synergy 可以较高，但 overall_risk 不应因此自动升高；必须区分“金融相关性”和“金融风险性”。

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

三、情感标签体系 SENTIMENT_LABELS：
{json.dumps(SENTIMENT_LABELS, ensure_ascii=False, indent=2)}

情感风险映射：
1. 中性：通常为无风险。
2. 负面-恐慌/恶意唱空：高风险。
3. 负面-理性担忧：低风险。
4. 正面-理性看好：低风险。
5. 正面-过度狂热：高风险。

四、煽动性评分准则：
1. tone_score：语气强度，0-40。依据感叹号、极端词、绝对化表达、夸张表达、强行动号召评分。
2. scarcity_score：稀缺/紧迫暗示，0-30。依据“限时、限量、最后机会、倒计时、错过不再”等表达评分。
3. herd_score：从众诱导，0-30。依据“大家都在买、万人参与、爆款、刷屏、强烈推荐”等表达评分。
4. total_score = tone_score + scarcity_score + herd_score，范围 0-100。
5. 煽动性等级 INCITEMENT_LEVELS：
{json.dumps(INCITEMENT_LEVELS, ensure_ascii=False, indent=2)}

五、图像特征评分准则：
1. ocr_text：只提取图片中真实可见文字；看不清则填空字符串。
2. qr_result：只有图片中真实可见二维码时 qr_detected 才能为 true。
3. contact_detected：图片中真实出现微信、电话、网址、群聊、客服、私信等联系方式时为 true。
4. visual_marketing_score：0-100，衡量是否像营销海报、收益截图、课程广告、开户链接、理财产品宣传。
5. financial_visual_score：0-100，衡量图片视觉内容是否指向金融、理财、股票、基金、保险、期货、数字货币等主题。

六、多模态融合要求：
你必须完成特征融合，而不是只分别分析文本和图片。需要给出：
1. semantic_consistency：正文与图片/OCR语义一致性，0-100。
2. risk_alignment：正文风险类别与OCR风险类别是否对齐，0-100。
3. finance_synergy：正文、图片、OCR是否共同指向金融主题，0-100。
4. drainage_linkage：正文风险与二维码/联系方式/私域导流是否联动，0-100。
5. persuasion_coupling：文本煽动性、OCR话术、视觉营销是否互相强化，0-100。
6. fused_feature_vector：融合后的输入特征向量，feature_names 与 values 长度必须一致。
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
3. reasons 至少给出 3 条可解释证据；低风险也要说明低风险依据。
4. 不要编造图片中不存在的文字、二维码、联系方式或金融元素。
5. 如果样本只表现为正常金融科普、产品常识、理性投资讨论或风险教育，且没有引流/诈骗/夸大收益/紧迫逼单等证据，total_score 应控制在 0-39，risk_level 为低风险。
6. 只输出 JSON 对象，不要输出 Markdown、代码块或额外说明。

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


AliyunRiskAnalyzer = AliyunMultimodalRiskAnalyzer
ChatGPTRiskAnalyzer = AliyunMultimodalRiskAnalyzer


def print_result(result: Dict[str, Any], model: str) -> None:
    final = result.get("final_multimodal_analysis", {})
    fusion = result.get("multimodal_feature_fusion", {})
    network = result.get("fusion_network_analysis", {})

    print("=" * 72)
    print("多模态网络金融舆情风险监测结果")
    print("=" * 72)
    print(f"模型: {model}")
    elapsed = result.get("runtime", {}).get("aliyun_remote_elapsed_seconds")
    if elapsed is not None:
        print(f"阿里远端耗时: {elapsed:.3f} 秒")
    print(f"总分: {final.get('total_score', '')}")
    print(f"风险等级: {final.get('risk_level', '')}")
    print(f"结论: {final.get('conclusion', '')}")

    print("\n模态分解得分:")
    for key, value in fusion.get("modality_breakdown", {}).items():
        print(f"  {key}: {value}")

    print("\n跨模态融合特征:")
    for key, value in fusion.get("cross_modal_features", {}).items():
        if isinstance(value, list):
            value = ", ".join(map(str, value)) if value else "无"
        print(f"  {key}: {value}")

    print("\n融合网络输出层:")
    for key, value in network.get("output_layer", {}).items():
        print(f"  {key}: {value}")

    print("\n关键证据:")
    for reason in final.get("reasons", [])[:10]:
        print(f"  - {reason}")

    print("\n完整 JSON:")
    print(json.dumps(result, ensure_ascii=False, indent=2))


def main() -> int:
    text = (
        "美股指数基金主要投资于指数成份股，这些成份股通常会覆盖多个行业和板块，"
        "所以能分散风险，长期收益较稳定，而且操作简单方便，对个人投资者比较友好。"
        "我们在选择指数基金的时候，首先需要明确投资目标、投资期限、预期收益和风险承受能力。"
        "你是保守保本型，稳健固收型，还是权益增长型。也可以选择标普、纳指、国债等指数。"
        "如果对科技、人工智能、AI行业感兴趣，可以选择纳指100。"
        "指数基金费用、历史业绩、年化收益率和波动率都可以作为参考。"
        "#香港理财财富管理##保险基金#"
    )
    pic = r"多模态模型\3.模型整合\pics\5250024851118516-7.jpg"

    analyzer = AliyunMultimodalRiskAnalyzer()
    result = analyzer.analyze(post_text=text, image_path=pic)
    print_result(result, analyzer.model)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
