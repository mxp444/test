const reportStatus = document.querySelector("#reportStatus");
const reportMeta = document.querySelector("#reportMeta");
const reportContent = document.querySelector("#reportContent");

const outputLabels = {
  overall_risk: "总体风险",
  financial_risk: "金融风险",
  drainage_risk: "引流风险",
  marketing_risk: "营销诱导",
  consistency_risk: "图文一致性风险",
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

const objectLabels = {
  qr_detected: "是否检测到二维码",
  qr_data: "二维码内容",
  blur_raw: "原始模糊度",
  clarity_score: "清晰度",
  color_score: "色彩丰富度",
  design_score: "设计感",
  sentiment: "情感标签",
  risk_level: "风险等级",
  confidence: "置信度",
  status: "状态",
  message: "说明",
};

loadReport();

async function loadReport() {
  const id = new URLSearchParams(location.search).get("id");
  if (!id) {
    showError("缺少报告 id。");
    return;
  }

  try {
    const response = await fetch(`/api/items/${encodeURIComponent(id)}`);
    const payload = await response.json();
    if (!response.ok || !payload.ok) throw new Error(payload.error || "报告读取失败。");
    renderReport(payload.item);
  } catch (error) {
    showError(error.message);
  }
}

function renderReport(item) {
  const data = item.analysis || {};
  const summary = data.summary || {};
  const text = data.text_feature_extraction || {};
  const image = data.image_feature_extraction || {};
  const ocr = data.ocr_text_feature_extraction || {};
  const fusion = data.multimodal_feature_fusion || {};

  reportStatus.textContent = summary.risk_level || "已加载";
  reportStatus.className = "status-pill ok";
  reportMeta.textContent = `${item.screen_name || "未知用户"} · ${item.created_at || ""}`;

  reportContent.innerHTML = `
    <section class="report-card">
      <div class="score-grid">
        <div><span>综合风险分</span><strong>${formatScore(summary.total_score)}</strong></div>
        <div><span>风险等级</span><strong>${escapeHtml(summary.risk_level || "--")}</strong></div>
      </div>
      <p class="conclusion">${escapeHtml(summary.conclusion || "暂无结论")}</p>
      <p class="text-box">${escapeHtml(summary.suggestion || "")}</p>
    </section>

    ${renderBlock(`${item.platform_name || platformLabel(item.platform) || "平台"}原文`, `<p class="text-box">${escapeHtml(item.text || "")}</p>${renderPics(item.pics || [])}`)}
    ${renderBlock("融合网络输出层", `<div class="bars">${renderBars(summary.network_output || {}, outputLabels)}</div>`)}
    ${renderBlock("融合输入特征向量", `<div class="metric-grid">${renderVector(fusion.fused_feature_vector || {})}</div>`)}
    ${renderBlock("跨模态融合特征", `<div class="feature-list">${renderFeatureList(summary.cross_modal_features || {}, crossLabels)}</div>`)}
    ${renderBlock("关键证据", renderList(summary.reasons || []))}
    ${renderBlock("正文文本分析", `<div class="analysis-grid">${renderTextAnalysis(text)}</div>`)}
    ${renderBlock("图片视觉与 OCR 结果", `<div class="analysis-grid">${renderImageAnalysis(image)}</div>`)}
    ${renderBlock("OCR 文本分析", `<div class="analysis-grid">${renderTextAnalysis(ocr, true)}</div>`)}
    ${renderBlock("模型组件状态", `<div class="component-status">${renderComponentStatus(data.runtime || {})}</div>`)}
    ${renderBlock("完整结构化 JSON", `<pre>${escapeHtml(JSON.stringify(data, null, 2))}</pre>`)}
  `;
}

function renderBlock(title, html) {
  return `<section class="report-card"><h2>${escapeHtml(title)}</h2>${html}</section>`;
}

function renderPics(pics) {
  const html = pics.map((pic) => `<img src="${pic.url}" title="${escapeHtml(pic.path)}" loading="lazy">`).join("");
  return html ? `<div class="pics">${html}</div>` : "";
}

function platformLabel(value) {
  return {
    weibo: "微博",
    douyin: "抖音",
    tieba: "百度贴吧",
    xhs: "小红书",
  }[value] || value || "";
}

function renderBars(values, labels) {
  const entries = Object.entries(values);
  if (!entries.length) return "<p class=\"text-box\">暂无输出层评分。</p>";
  return entries.map(([key, value]) => {
    const score = clamp(Number(value) || 0, 0, 100);
    return `
      <div class="bar-row">
        <div class="bar-head"><strong>${escapeHtml(labelFor(key, labels))}</strong><span>${formatScore(score)}</span></div>
        <div class="bar-track"><div class="bar-fill" style="width: ${score}%"></div></div>
      </div>
    `;
  }).join("");
}

function renderVector(vector) {
  const names = Array.isArray(vector.feature_names) ? vector.feature_names : [];
  const values = Array.isArray(vector.values) ? vector.values : [];
  if (!names.length) return "<p class=\"text-box\">暂无融合输入特征。</p>";
  return names.map((name, index) => `
    <div class="metric-item"><span>${escapeHtml(name)}</span><strong>${formatScore(values[index])}</strong></div>
  `).join("");
}

function renderTextAnalysis(result, isOcr = false) {
  const rawText = result.raw_text || "";
  if (isOcr && !rawText) return "<p class=\"text-box\">未识别到图片文字，OCR 文本模型未产生有效文本特征。</p>";
  return `
    ${section("分析文本", `<p class="text-box">${escapeHtml(rawText || "无")}</p>`)}
    ${section("综合评分", renderFeatureList(result.scores || {}, scoreLabels))}
    ${section("金融属性 Top4", renderFinanceTopk(result.finance_topk || []))}
    ${section("风险要素评分", renderBars(result.risk_factor_scores || {}, {}))}
    ${section("情感分析", renderObjectSummary(result.sentiment || {}))}
    ${section("煽动性评估", renderObjectSummary(result.incitement || {}))}
    ${section("风险证据", renderList(result.evidence || []))}
  `;
}

function renderImageAnalysis(result) {
  return `
    ${section("OCR 识别文字", `<p class="text-box">${escapeHtml(result.ocr_text || "无")}</p>`)}
    ${section("图片综合评分", renderFeatureList(result.scores || {}, scoreLabels))}
    ${section("视觉指标", renderObjectSummary(result.visual_metrics || {}))}
    ${section("二维码检测", renderObjectSummary(result.qr_result || {}))}
    ${section("视觉标签", renderList(result.visual_tags || []))}
    ${section("图片证据", renderList(result.evidence || []))}
  `;
}

function section(title, html) {
  return `<div class="analysis-section"><h4>${escapeHtml(title)}</h4>${html}</div>`;
}

function renderFeatureList(values, labels) {
  const entries = Object.entries(values || {});
  if (!entries.length) return "<p class=\"text-box\">暂无结果。</p>";
  return entries.map(([key, value]) => `
    <div class="feature-row"><span>${escapeHtml(labelFor(key, labels))}</span><strong>${escapeHtml(formatValue(value))}</strong></div>
  `).join("");
}

function renderFinanceTopk(items) {
  if (!Array.isArray(items) || !items.length) return "<p class=\"text-box\">暂无金融属性结果。</p>";
  return items.map((item) => `
    <div class="feature-row"><span>${escapeHtml(item.label || `类别 ${item.label_id}`)}</span><strong>${formatPercent(item.confidence)}</strong></div>
  `).join("");
}

function renderObjectSummary(value) {
  return renderFeatureList(Object.fromEntries(Object.entries(value || {}).filter(([key]) => key !== "raw")), objectLabels);
}

function renderList(items) {
  if (!Array.isArray(items) || !items.length) return "<p class=\"text-box\">无</p>";
  return `<ul class="mini-list">${items.map((item) => `<li>${escapeHtml(formatValue(item))}</li>`).join("")}</ul>`;
}

function renderComponentStatus(runtime) {
  const statuses = runtime.component_status || {};
  const seconds = runtime.component_load_seconds || {};
  return Object.entries(statuses).map(([name, status]) => `
    <div class="component-row"><span>${escapeHtml(name)}</span><strong>${escapeHtml(status)}</strong><em>${formatScore(seconds[name])}s</em></div>
  `).join("") || "<p class=\"text-box\">暂无组件状态。</p>";
}

function showError(message) {
  reportStatus.textContent = "加载失败";
  reportStatus.className = "status-pill error";
  reportContent.innerHTML = `<p class="error-text">${escapeHtml(message)}</p>`;
}

function labelFor(key, labels = {}) {
  return labels[key] || key;
}

function formatScore(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number.toFixed(2) : "--";
}

function formatPercent(value) {
  const number = Number(value);
  return Number.isFinite(number) ? `${(number * 100).toFixed(1)}%` : "--";
}

function formatValue(value) {
  if (Array.isArray(value)) return value.length ? value.map(formatValue).join("，") : "无";
  if (value && typeof value === "object") return JSON.stringify(value);
  if (typeof value === "number") return Number.isFinite(value) ? value.toFixed(4).replace(/\.?0+$/, "") : "--";
  if (typeof value === "boolean") return value ? "是" : "否";
  return String(value ?? "--");
}

function clamp(value, low, high) {
  return Math.max(low, Math.min(high, value));
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;",
  }[char]));
}
