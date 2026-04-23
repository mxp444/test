const form = document.querySelector("#analysisForm");
const postText = document.querySelector("#postText");
const imageInput = document.querySelector("#imageInput");
const uploadHint = document.querySelector("#uploadHint");
const previewImage = document.querySelector("#previewImage");
const submitBtn = document.querySelector("#submitBtn");
const healthStatus = document.querySelector("#healthStatus");

const emptyState = document.querySelector("#emptyState");
const loadingState = document.querySelector("#loadingState");
const resultContent = document.querySelector("#resultContent");
const totalScore = document.querySelector("#totalScore");
const riskLevel = document.querySelector("#riskLevel");
const conclusion = document.querySelector("#conclusion");
const suggestion = document.querySelector("#suggestion");
const networkOutput = document.querySelector("#networkOutput");
const fusionVector = document.querySelector("#fusionVector");
const crossFeatures = document.querySelector("#crossFeatures");
const reasons = document.querySelector("#reasons");
const textAnalysis = document.querySelector("#textAnalysis");
const imageAnalysis = document.querySelector("#imageAnalysis");
const ocrAnalysis = document.querySelector("#ocrAnalysis");
const componentStatus = document.querySelector("#componentStatus");
const rawJson = document.querySelector("#rawJson");

const outputLabels = {
  overall_risk: "总体风险",
  financial_risk: "金融风险",
  drainage_risk: "引流风险",
  marketing_risk: "营销诱导",
  consistency_risk: "图文一致性风险",
};

const crossLabels = {
  semantic_consistency: "语义一致性",
  risk_alignment: "风险类别对齐",
  finance_synergy: "金融主题协同",
  drainage_linkage: "引流联动",
  persuasion_coupling: "诱导耦合",
  shared_keywords: "共享关键词",
  shared_risk_categories: "共享风险类别",
  text_image_reinforcement: "图文强化关系",
  contradictions: "矛盾信号",
};

const scoreLabels = {
  financial_score: "金融属性",
  risk_factor_score: "风险要素",
  sentiment_score: "情感风险",
  incitement_score: "煽动性",
  overall_score: "综合得分",
  diversion_score: "引流风险",
  visual_marketing_score: "视觉营销",
  financial_visual_score: "金融视觉",
};

const incitementLabels = {
  tone_score: "语气强度",
  scarcity_score: "稀缺紧迫",
  herd_score: "从众暗示",
  total_score: "煽动总分",
};

const riskLabels = {
  principal_guarantee: "保本无风险虚假承诺",
  high_return: "超高收益诱导",
  pyramid_rebate: "拉人头层级返利",
  insider_recommendation: "内幕消息违规荐股",
  urgency_scarcity: "紧迫稀缺营销逼单",
  authority_endorsement: "虚假资质权威背书",
  crypto_asset: "虚拟货币/数字资产诈骗",
  credit_loan: "征信修复/贷款诈骗",
  private_domain_drainage: "私域引流联系方式",
  herd_inducement: "虚假造势从众诱导",
  illegal_foreign_trading: "非法外盘/跨境金融交易",
  pension_scam: "养老金融诈骗",
  ponzi_scheme: "资金盘/庞氏骗局特征",
  entrusted_finance: "代客理财违规操作",
  nft_metaverse: "数字藏品/元宇宙金融骗局",
  leverage_allocation: "股票/期货配资违规交易",
};

const featureLabels = {
  text_financial_score: "正文金融属性分",
  text_risk_factor_score: "正文风险要素分",
  text_sentiment_score: "正文情感风险分",
  text_incitement_score: "正文煽动性分",
  text_overall_score: "正文综合分",
  image_diversion_score: "图片引流分",
  image_visual_marketing_score: "图片视觉营销分",
  image_financial_visual_score: "图片金融视觉分",
  image_overall_score: "图片综合分",
  ocr_financial_score: "OCR 金融属性分",
  ocr_risk_factor_score: "OCR 风险要素分",
  ocr_sentiment_score: "OCR 情感风险分",
  ocr_incitement_score: "OCR 煽动性分",
  ocr_overall_score: "OCR 综合分",
  semantic_consistency: "图文语义一致性",
  risk_alignment: "风险类别对齐",
  finance_synergy: "金融主题协同",
  drainage_linkage: "引流联动",
  persuasion_coupling: "诱导耦合",
  text_image_reinforcement_count: "图文强化数量",
  qr_detected: "二维码命中",
};

const objectLabels = {
  elapsed_seconds: "耗时",
  json_path: "JSON 文件",
  status: "状态",
  message: "说明",
  qr_detected: "是否检测到二维码",
  qr_data: "二维码内容",
  qr_bbox: "二维码位置",
  blur_raw: "原始模糊度",
  clarity_score: "清晰度",
  color_score: "色彩丰富度",
  design_score: "设计感",
  design_std: "设计感波动",
  text: "文本",
  sentiment: "情感标签",
  label_id: "标签编号",
  risk_level: "风险等级",
  confidence: "置信度",
};

const statusLabels = {
  generated: "已生成",
  cached: "读取缓存",
  unavailable: "不可用",
  error: "失败",
  timeout: "超时",
  cached_after_error: "失败后读取缓存",
  cached_after_timeout: "超时后读取缓存",
  model: "模型",
  fallback: "规则兜底",
  failed: "加载失败",
};

checkHealth();

imageInput.addEventListener("change", () => {
  const file = imageInput.files[0];
  if (!file) {
    uploadHint.textContent = "支持 jpg、jpeg、png、bmp、webp";
    previewImage.style.display = "none";
    previewImage.removeAttribute("src");
    return;
  }

  uploadHint.textContent = file.name;
  previewImage.src = URL.createObjectURL(file);
  previewImage.style.display = "block";
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();

  const file = imageInput.files[0];
  if (!postText.value.trim()) {
    alert("请输入待检测文本。");
    return;
  }
  if (!file) {
    alert("请上传一张图片。");
    return;
  }

  const formData = new FormData();
  formData.append("post_text", postText.value.trim());
  formData.append("image", file);

  setLoading(true);

  try {
    const response = await fetch("/analyze", {
      method: "POST",
      body: formData,
    });
    const payload = await response.json();

    if (!response.ok || !payload.success) {
      throw new Error(payload.error || "分析失败。");
    }

    renderResult(payload.data);
  } catch (error) {
    alert(error.message);
    showEmpty();
  } finally {
    setLoading(false);
  }
});

async function checkHealth() {
  try {
    const response = await fetch("/health");
    const payload = await response.json();
    if (!response.ok || !payload.success) throw new Error("服务异常");
    healthStatus.textContent = payload.model_ready ? "模型引擎就绪" : "模型引擎待配置";
    healthStatus.classList.add(payload.model_ready ? "is-ok" : "is-warn");
  } catch {
    healthStatus.textContent = "后端服务未连接";
    healthStatus.classList.add("is-error");
  }
}

function setLoading(isLoading) {
  submitBtn.disabled = isLoading;
  submitBtn.querySelector("span").textContent = isLoading ? "分析中..." : "运行风险监测";
  emptyState.classList.toggle("hidden", isLoading);
  loadingState.classList.toggle("hidden", !isLoading);
  if (isLoading) resultContent.classList.add("hidden");
}

function showEmpty() {
  emptyState.classList.remove("hidden");
  loadingState.classList.add("hidden");
  resultContent.classList.add("hidden");
}

function renderResult(data) {
  const summary = data.summary || {};
  emptyState.classList.add("hidden");
  loadingState.classList.add("hidden");
  resultContent.classList.remove("hidden");

  totalScore.textContent = formatScore(summary.total_score);
  riskLevel.textContent = summary.risk_level || "--";
  conclusion.textContent = summary.conclusion || "暂无结论";
  suggestion.textContent = summary.suggestion || "";

  const fusion = data.multimodal_feature_fusion || {};
  const text = data.text_feature_extraction || {};
  const image = data.image_feature_extraction || {};
  const ocr = data.ocr_text_feature_extraction || {};

  networkOutput.innerHTML = renderBars(summary.network_output || {}, outputLabels);
  fusionVector.innerHTML = renderVector(fusion.fused_feature_vector || {});
  crossFeatures.innerHTML = renderFeatureList(summary.cross_modal_features || {}, crossLabels);

  const evidence = Array.isArray(summary.reasons) ? summary.reasons : [];
  reasons.innerHTML = evidence.length
    ? evidence.slice(0, 10).map((item) => `<li>${escapeHtml(String(item))}</li>`).join("")
    : "<li>暂无关键证据。</li>";

  textAnalysis.innerHTML = renderTextAnalysis(text, false, false);
  imageAnalysis.innerHTML = renderImageAnalysis(image);
  ocrAnalysis.innerHTML = renderTextAnalysis(ocr, true);
  componentStatus.innerHTML = renderComponentStatus(data.runtime || {});
  rawJson.textContent = JSON.stringify(data, null, 2);
}

function renderBars(values, labels) {
  const entries = Object.entries(values);
  if (!entries.length) return "<p class=\"muted\">暂无输出层评分。</p>";
  return entries
    .map(([key, value]) => {
      const score = clamp(Number(value) || 0, 0, 100);
      return `
        <div class="bar-row">
          <div class="bar-head">
            <strong>${escapeHtml(labelFor(key, labels))}</strong>
            <span>${formatScore(score)}</span>
          </div>
          <div class="bar-track"><div class="bar-fill" style="width: ${score}%"></div></div>
        </div>
      `;
    })
    .join("");
}

function renderChips(values, labels, asRatio = false) {
  const entries = Object.entries(values);
  if (!entries.length) return "<p class=\"muted\">暂无模态分解结果。</p>";
  return entries
    .map(([key, value]) => {
      const shown = asRatio ? formatRatio(value) : formatScore(value);
      return `
        <div class="chip">
          <span>${escapeHtml(labelFor(key, labels))}</span>
          <strong>${shown}</strong>
        </div>
      `;
    })
    .join("");
}

function renderFeatureList(values, labels) {
  const entries = Object.entries(values);
  if (!entries.length) return "<p class=\"muted\">暂无跨模态融合特征。</p>";
  return entries
    .map(([key, value]) => {
      const shown = Array.isArray(value) ? (value.length ? value.join("，") : "无") : value;
      return `
        <div class="feature-row">
          <span>${escapeHtml(labelFor(key, labels))}</span>
          <strong>${escapeHtml(formatValue(shown))}</strong>
        </div>
      `;
    })
    .join("");
}

function renderVector(vector) {
  const names = Array.isArray(vector.feature_names) ? vector.feature_names : [];
  const values = Array.isArray(vector.values) ? vector.values : [];
  if (!names.length) return "<p class=\"muted\">暂无融合输入特征。</p>";

  return names
    .map((name, index) => `
      <div class="metric-item">
        <span>${escapeHtml(labelFor(name, featureLabels))}</span>
        <strong>${formatScore(values[index])}</strong>
      </div>
    `)
    .join("");
}

function renderTextAnalysis(result, isOcr = false, showRawText = true) {
  const rawText = result.raw_text || "";
  if (isOcr && !rawText) {
    return "<p class=\"muted\">未识别到图片文字，OCR 文本模型未产生有效文本特征。</p>";
  }

  return `
    ${showRawText ? renderRawText(rawText, isOcr ? "识别文本" : "输入文本") : ""}
    ${renderSection("综合评分", renderChips(result.scores || {}, scoreLabels))}
    ${renderSection("金融属性 Top4", renderFinanceTopk(result.finance_topk || []))}
    ${renderSection("风险要素评分", renderRiskScores(result.risk_factor_scores || {}))}
    ${renderSection("情感分析", renderObjectSummary(result.sentiment || {}))}
    ${renderSection("煽动性评估", renderIncitement(result.incitement || {}))}
    ${renderSection("风险证据", renderList(result.evidence || []))}
  `;
}

function renderImageAnalysis(result) {
  return `
    ${renderRawText(result.ocr_text || "", "OCR 识别文字")}
    ${renderSection("图片综合评分", renderChips(result.scores || {}, scoreLabels))}
    ${renderSection("视觉指标", renderObjectSummary(result.visual_metrics || {}))}
    ${renderSection("二维码检测", renderObjectSummary(result.qr_result || {}))}
    ${renderSection("视觉标签", renderList(result.visual_tags || []))}
    ${renderSection("图片证据", renderList(result.evidence || []))}
  `;
}

function renderSection(title, html) {
  return `
    <div class="analysis-section">
      <h4>${escapeHtml(title)}</h4>
      ${html}
    </div>
  `;
}

function renderRawText(text, title) {
  const value = String(text || "").trim();
  return `
    <div class="analysis-section">
      <h4>${escapeHtml(title)}</h4>
      <p class="text-box">${value ? escapeHtml(value) : "无"}</p>
    </div>
  `;
}

function renderFinanceTopk(items) {
  if (!Array.isArray(items) || !items.length) return "<p class=\"muted\">暂无金融属性结果。</p>";
  return items
    .map((item) => `
      <div class="feature-row">
        <span>${escapeHtml(item.label || `类别 ${item.label_id}`)}</span>
        <strong>${formatRatio(item.confidence)}</strong>
      </div>
    `)
    .join("");
}

function renderRiskScores(scores) {
  const entries = Object.entries(scores);
  if (!entries.length) return "<p class=\"muted\">暂无风险要素评分。</p>";
  return renderBars(scores, riskLabels);
}

function renderIncitement(incitement) {
  const summary = {
    tone_score: incitement.tone_score,
    scarcity_score: incitement.scarcity_score,
    herd_score: incitement.herd_score,
    total_score: incitement.total_score,
  };
  return `
    ${renderChips(summary, incitementLabels)}
    <div class="feature-row">
      <span>风险等级</span>
      <strong>${escapeHtml(String(incitement.risk_level || "--"))}</strong>
    </div>
  `;
}

function renderObjectSummary(value) {
  const entries = Object.entries(value || {}).filter(([key]) => key !== "raw");
  if (!entries.length) return "<p class=\"muted\">暂无结果。</p>";
  return entries
    .map(([key, item]) => `
      <div class="feature-row">
        <span>${escapeHtml(labelFor(key, objectLabels))}</span>
        <strong>${escapeHtml(formatValue(item))}</strong>
      </div>
    `)
    .join("");
}

function renderList(items) {
  if (!Array.isArray(items) || !items.length) return "<p class=\"muted\">无</p>";
  return `<ul class="mini-list">${items.map((item) => `<li>${escapeHtml(formatValue(item))}</li>`).join("")}</ul>`;
}

function renderComponentStatus(runtime) {
  const statuses = runtime.component_status || {};
  const seconds = runtime.component_load_seconds || {};
  const entries = Object.entries(statuses);
  if (!entries.length) return "<p class=\"muted\">暂无组件状态。</p>";

  return entries
    .map(([name, status]) => {
      const elapsed = Number(seconds[name]);
      const elapsedText = Number.isFinite(elapsed) ? `${elapsed.toFixed(3)}s` : "--";
      const className = status === "model" ? "ok" : status === "fallback" ? "warn" : "error";
      return `
        <div class="component-row">
          <span>${escapeHtml(formatComponentName(name))}</span>
          <strong class="${className}">${escapeHtml(statusLabels[status] || status)}</strong>
          <em>${elapsedText}</em>
        </div>
      `;
    })
    .join("");
}

function formatScore(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number.toFixed(2) : "--";
}

function formatRatio(value) {
  const number = Number(value);
  return Number.isFinite(number) ? `${(number * 100).toFixed(1)}%` : "--";
}

function formatValue(value) {
  if (Array.isArray(value)) return value.length ? value.map(formatValue).join("，") : "无";
  if (value && typeof value === "object") return JSON.stringify(value);
  if (typeof value === "number") return Number.isFinite(value) ? value.toFixed(4).replace(/\.?0+$/, "") : "--";
  if (typeof value === "boolean") return value ? "是" : "否";
  const text = String(value ?? "--");
  return statusLabels[text] || text;
}

function labelFor(key, labels = {}) {
  return labels[key] || riskLabels[key] || featureLabels[key] || objectLabels[key] || key;
}

function formatComponentName(name) {
  return String(name)
    .replace("nlp金融属性判断.Financial_attribute", "金融属性判断")
    .replace("nlp风险要素识别.Risk_factor", "风险要素识别")
    .replace("nlp情感分析.Sentiment_analysis", "情感分析")
    .replace("nlp煽动性评估.Incitement_evaluator", "煽动性评估")
    .replace("picOCR文字识别.OCR", "OCR 文字识别")
    .replace("pic二维码检测.QR_code_detector", "二维码检测")
    .replace("pic模糊度检测.Ambiguity", "图片模糊度检测")
    .replace("pic色彩丰富程度.Color_richness", "色彩丰富度检测")
    .replace("pic设计感.Design_sense", "图片设计感检测");
}

function clamp(value, low, high) {
  return Math.max(low, Math.min(high, value));
}

function escapeHtml(value) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
