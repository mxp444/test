# -*- coding: utf-8 -*-
import importlib.util
import sys
from pathlib import Path
from uuid import uuid4

from flask import Flask, jsonify, request, send_from_directory
from werkzeug.utils import secure_filename


BASE_DIR = Path(__file__).resolve().parents[1]
FRONTEND_DIR = BASE_DIR / "frontend"
UPLOAD_DIR = BASE_DIR / "backend" / "uploads"
ENGINE_FILE = BASE_DIR / "多模态融合分析.py"
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def load_analyzer_class():
    if not ENGINE_FILE.exists():
        raise RuntimeError(f"没有找到多模态融合分析文件: {ENGINE_FILE}")
    if str(BASE_DIR) not in sys.path:
        sys.path.insert(0, str(BASE_DIR))

    spec = importlib.util.spec_from_file_location("local_multimodal_fusion", ENGINE_FILE)
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载多模态融合分析模块。")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    analyzer_cls = getattr(module, "MultimodalRiskFusion", None)
    if analyzer_cls is None:
        raise RuntimeError("多模态融合分析.py 中没有 MultimodalRiskFusion 类。")
    return analyzer_cls


AnalyzerClass = load_analyzer_class()
risk_engine = AnalyzerClass(base_dir=str(BASE_DIR), strict_init=True)
app = Flask(__name__, static_folder=str(FRONTEND_DIR), static_url_path="")


def get_risk_engine():
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
        "runtime": result.get("runtime", {}),
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
    if "No module named" in raw:
        return f"本地模型依赖或模块缺失: {raw}"
    if "CUDA" in raw or "torch" in raw:
        return f"本地深度学习模型加载失败: {raw}"
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
            "model_ready": True,
            "engine": "MultimodalRiskFusion",
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
        if isinstance(exc, ValueError):
            return jsonify({"success": False, "error": public_error_message(exc)}), 400
        raise


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True, use_reloader=False)

"""
美股指数基金主要投资于指数成份股，这些成份股通常会覆盖多个行业和板块，
所以能分散风险，长期收益较稳定，而且操作简单方便，对个人投资者比较友好。
我们在选择指数基金的时候，首先需要明确投资目标、投资期限、预期收益和风险承受能力。
你是保守保本型，稳健固收型，还是权益增长型。也可以选择标普、纳指、国债等指数。
如果对科技、人工智能、AI行业感兴趣，可以选择纳指100。
指数基金费用、历史业绩、年化收益率和波动率都可以作为参考。
#香港理财财富管理##保险基金#
"""
