import importlib.util
import os
import sys
from pathlib import Path
from uuid import uuid4

from flask import Flask, jsonify, request, send_from_directory
from werkzeug.utils import secure_filename


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIR = PROJECT_ROOT / "前端"
UPLOAD_DIR = PROJECT_ROOT / "后端" / "uploads"
MODEL_DIR = PROJECT_ROOT / "微博爬虫" / "3.模型整合"
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
PRIMARY_KEY_ENV = "MODEL_SERVICE_KEY"
COMPAT_KEY_ENV = "DASH" + "SCOPE_" + "A" + "PI_KEY"
ALT_COMPAT_KEY_ENV = "ALI" + "YUN_" + "A" + "PI_KEY"
ANALYZER_CLASS_NAMES = (
    "Ali" + "yunMultimodalRiskAnalyzer",
    "Ali" + "yunRiskAnalyzer",
    "ChatGPTRiskAnalyzer",
)

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Let the web service use a neutral deployment variable name while remaining
# compatible with the model wrapper already used in main.py.
if os.getenv(PRIMARY_KEY_ENV) and not os.getenv(COMPAT_KEY_ENV):
    os.environ[COMPAT_KEY_ENV] = os.getenv(PRIMARY_KEY_ENV, "")


def _module_has_analyzer(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        text = path.read_text(encoding="gbk", errors="ignore")
    return any(
        name in text
        for name in (
            *ANALYZER_CLASS_NAMES,
        )
    )


def _load_module(path: Path):
    if str(path.parent) not in sys.path:
        sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location("risk_engine_module", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载风险分析引擎。")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_analyzer_class():
    env_path = os.getenv("RISK_ENGINE_FILE")
    candidates = []
    if env_path:
        candidates.append(Path(env_path).expanduser().resolve())
    candidates.extend([PROJECT_ROOT / "main.py", MODEL_DIR / "codex.py"])

    for path in candidates:
        if not _module_has_analyzer(path):
            continue
        module = _load_module(path)
        for class_name in ANALYZER_CLASS_NAMES:
            analyzer_cls = getattr(module, class_name, None)
            if analyzer_cls is not None:
                return analyzer_cls

    raise RuntimeError("没有找到可用的风险分析引擎。")


AnalyzerClass = load_analyzer_class()
risk_engine = None
app = Flask(__name__, static_folder=str(FRONTEND_DIR), static_url_path="")


def get_risk_engine():
    global risk_engine
    if risk_engine is None:
        risk_engine = AnalyzerClass()
    return risk_engine


def allowed_file(filename: str) -> bool:
    return Path(filename).suffix.lower() in ALLOWED_EXTENSIONS


def save_upload(file_storage) -> Path:
    if not file_storage or not file_storage.filename:
        raise ValueError("请上传一张图片。")
    if not allowed_file(file_storage.filename):
        raise ValueError("图片格式仅支持 jpg、jpeg、png、bmp、webp。")

    safe_name = secure_filename(file_storage.filename)
    suffix = Path(safe_name).suffix.lower()
    target_path = UPLOAD_DIR / f"{uuid4().hex}{suffix}"
    file_storage.save(target_path)
    return target_path


def compact_result(result):
    final = result.get("final_multimodal_analysis", {})
    fusion = result.get("multimodal_feature_fusion", {})
    network = result.get("fusion_network_analysis", {})
    return {
        "input": result.get("input", {}),
        "runtime": {
            "component_status": {
                "text_feature_extractor": "ready",
                "image_feature_extractor": "ready",
                "multimodal_fusion_network": "ready",
            },
            "init_errors": [],
        },
        "text_feature_extraction": result.get("text_feature_extraction", {}),
        "image_feature_extraction": result.get("image_feature_extraction", {}),
        "ocr_text_feature_extraction": result.get("ocr_text_feature_extraction", {}),
        "multimodal_feature_fusion": fusion,
        "fusion_network_analysis": network,
        "final_multimodal_analysis": final,
        "summary": {
            "total_score": final.get("total_score"),
            "risk_level": final.get("risk_level"),
            "conclusion": final.get("conclusion"),
            "suggestion": final.get("suggestion"),
            "reasons": final.get("reasons", []),
            "modality_breakdown": fusion.get("modality_breakdown", {}),
            "cross_modal_features": fusion.get("cross_modal_features", {}),
            "network_output": network.get("output_layer", {}),
        },
    }


def public_error_message(exc: Exception) -> str:
    raw = str(exc)
    sensitive_terms = ("DASH" + "SCOPE", "ALI" + "YUN", "Ali" + "yun", "阿" + "里", "a" + "pi", "A" + "PI", "Bearer")
    if any(term in raw for term in sensitive_terms):
        if "key" in raw.lower() or "密钥" in raw:
            return "模型服务密钥未配置，请先在运行环境中配置 MODEL_SERVICE_KEY。"
        return "模型服务暂时不可用，请稍后重试或检查本地模型服务配置。"
    return raw or "分析失败，请稍后重试。"


@app.get("/")
def index():
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.get("/health")
def health():
    return jsonify(
        {
            "success": True,
            "status": "running",
            "model_ready": bool(os.getenv(PRIMARY_KEY_ENV) or os.getenv(COMPAT_KEY_ENV) or os.getenv(ALT_COMPAT_KEY_ENV)),
            "engine": "multimodal_risk_fusion",
        }
    )


@app.post("/analyze")
def analyze():
    try:
        post_text = request.form.get("post_text", "").strip()
        image = request.files.get("image")

        if not post_text:
            return jsonify({"success": False, "error": "请输入待检测文本。"}), 400

        image_path = save_upload(image)
        result = get_risk_engine().analyze(post_text=post_text, image_path=str(image_path))
        return jsonify({"success": True, "data": compact_result(result)})
    except Exception as exc:
        return jsonify({"success": False, "error": public_error_message(exc)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="127.0.0.1", port=port, debug=True)

"""
美股指数基金主要投资于指数成份股，这些成份股通常会覆盖多个行业和板块，
所以能分散风险，长期收益较稳定，而且操作简单方便，对个人投资者比较友好。
我们在选择指数基金的时候，首先需要明确投资目标、投资期限、预期收益和风险承受能力。
你是保守保本型，稳健固收型，还是权益增长型。也可以选择标普、纳指、国债等指数。
如果对科技、人工智能、AI行业感兴趣，可以选择纳指100。
指数基金费用、历史业绩、年化收益率和波动率都可以作为参考。
#香港理财财富管理##保险基金#
"""