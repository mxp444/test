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
const modalityScores = document.querySelector("#modalityScores");
const crossFeatures = document.querySelector("#crossFeatures");
const reasons = document.querySelector("#reasons");
const componentStatus = document.querySelector("#componentStatus");
const rawJson = document.querySelector("#rawJson");

const outputLabels = {
  overall_risk: "总体风险",
  financial_risk: "金融风险",
  drainage_risk: "引流风险",
  marketing_risk: "营销诱导",
  consistency_risk: "图文一致性风险",
};

const modalityLabels = {
  post_text_score: "正文语义",
  image_score: "图像视觉",
  ocr_text_score: "图片文字",
  cross_modal_score: "跨模态交互",
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

  networkOutput.innerHTML = renderBars(summary.network_output || {}, outputLabels);
  modalityScores.innerHTML = renderChips(summary.modality_breakdown || {}, modalityLabels);
  crossFeatures.innerHTML = renderFeatureList(summary.cross_modal_features || {}, crossLabels);

  const evidence = Array.isArray(summary.reasons) ? summary.reasons : [];
  reasons.innerHTML = evidence.length
    ? evidence.slice(0, 10).map((item) => `<li>${escapeHtml(String(item))}</li>`).join("")
    : "<li>暂无关键证据。</li>";

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
          <strong>${escapeHtml(labels[key] || key)}</strong>
          <div class="bar-track"><div class="bar-fill" style="width: ${score}%"></div></div>
          <span>${formatScore(score)}</span>
        </div>
      `;
    })
    .join("");
}

function renderChips(values, labels) {
  const entries = Object.entries(values);
  if (!entries.length) return "<p class=\"muted\">暂无模态分解结果。</p>";
  return entries
    .map(([key, value]) => `<span class="chip">${escapeHtml(labels[key] || key)}：${formatScore(value)}</span>`)
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
          <span>${escapeHtml(labels[key] || key)}</span>
          <strong>${escapeHtml(String(shown))}</strong>
        </div>
      `;
    })
    .join("");
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
          <span>${escapeHtml(name)}</span>
          <strong class="${className}">${escapeHtml(status)}</strong>
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
