const toggleBtn = document.querySelector("#toggleBtn");
const refreshBtn = document.querySelector("#refreshBtn");
const analyzeOldBtn = document.querySelector("#analyzeOldBtn");
const runState = document.querySelector("#runState");
const lastResult = document.querySelector("#lastResult");
const lastError = document.querySelector("#lastError");
const logs = document.querySelector("#logs");
const count = document.querySelector("#count");
const items = document.querySelector("#items");
const healthStatus = document.querySelector("#healthStatus");
const metricInserted = document.querySelector("#metricInserted");
const metricSkipped = document.querySelector("#metricSkipped");
const metricUnmatched = document.querySelector("#metricUnmatched");
const metricDiscarded = document.querySelector("#metricDiscarded");
const platformInputs = Array.from(document.querySelectorAll("input[name='platform']"));

let currentStatus = { running: false, paused: false };
const openDetailIds = new Set();
const expandedTextIds = new Set();

checkHealth();
refreshAll();
setInterval(refreshAll, 10000);

toggleBtn.addEventListener("click", toggleCrawl);
refreshBtn.addEventListener("click", refreshAll);
analyzeOldBtn.addEventListener("click", analyzeOldItems);

async function checkHealth() {
  try {
    const response = await fetch("/health");
    const payload = await response.json();
    if (!response.ok || !payload.success) throw new Error(payload.error || "服务异常");
    const fallbackCount = Object.values(payload.component_status || {}).filter((value) => value !== "model").length;
    healthStatus.textContent = fallbackCount ? `模型就绪，${fallbackCount} 个组件使用兜底` : "模型引擎就绪";
    healthStatus.className = fallbackCount ? "status-pill warn" : "status-pill ok";
  } catch (error) {
    healthStatus.textContent = error.message || "后端服务未连接";
    healthStatus.className = "status-pill error";
  }
}

async function postJson(url, body) {
  const options = { method: "POST" };
  if (body !== undefined) {
    options.headers = { "Content-Type": "application/json" };
    options.body = JSON.stringify(body);
  }
  const res = await fetch(url, options);
  return res.json();
}

function selectedPlatforms() {
  const values = platformInputs.filter((input) => input.checked).map((input) => input.value);
  return values.length ? values : ["weibo"];
}

async function toggleCrawl() {
  toggleBtn.disabled = true;
  try {
    if (currentStatus.running && !currentStatus.paused) {
      await postJson("/api/crawl/pause");
    } else {
      await postJson("/api/crawl/start", { platforms: selectedPlatforms() });
    }
    await loadStatus();
  } finally {
    toggleBtn.disabled = false;
  }
}

async function analyzeOldItems() {
  analyzeOldBtn.disabled = true;
  analyzeOldBtn.textContent = "分析中...";
  try {
    const data = await postJson("/api/analyze/unprocessed?limit=20");
    if (!data.ok) throw new Error((data.errors || ["补分析失败"])[0]);
    await loadWeibos();
    alert(`已处理 ${data.processed || 0} 条历史数据。`);
  } catch (error) {
    alert(error.message);
  } finally {
    analyzeOldBtn.disabled = false;
    analyzeOldBtn.textContent = "补分析历史数据";
  }
}

async function loadStatus() {
  const res = await fetch("/api/crawl/status");
  const status = await res.json();
  currentStatus = status;

  if (status.running && status.paused) {
    runState.textContent = "已暂停";
    runState.className = "badge paused";
    toggleBtn.textContent = "继续";
    toggleBtn.className = "primary";
  } else if (status.running) {
    runState.textContent = "爬取与分析中";
    runState.className = "badge";
    toggleBtn.textContent = "暂停";
    toggleBtn.className = "warning";
  } else {
    runState.textContent = "空闲";
    runState.className = "badge idle";
    toggleBtn.textContent = "爬取";
    toggleBtn.className = "primary";
  }

  const stats = status.current_stats || status.last_result || {};
  platformInputs.forEach((input) => {
    input.disabled = Boolean(status.running);
    if (status.running) {
      input.checked = (status.selected_platforms || selectedPlatforms()).includes(input.value);
    }
  });
  metricInserted.textContent = stats.inserted || 0;
  metricSkipped.textContent = stats.skipped || 0;
  metricUnmatched.textContent = stats.unmatched || 0;
  metricDiscarded.textContent = stats.discarded || 0;

  if (status.last_result) {
    lastResult.textContent = `写入 ${status.last_result.inserted}，重复 ${status.last_result.skipped}，未命中 ${status.last_result.unmatched}，丢弃 ${status.last_result.discarded}`;
  } else if (status.running) {
    lastResult.textContent = `本轮实时统计：写入 ${stats.inserted || 0}，重复 ${stats.skipped || 0}，未命中 ${stats.unmatched || 0}，丢弃 ${stats.discarded || 0}`;
  } else {
    lastResult.textContent = "暂无结果";
  }

  lastError.textContent = status.last_error ? `错误：${status.last_error}` : "";
  logs.textContent = status.logs && status.logs.length ? status.logs.join("\n") : "等待爬取任务启动...";
  logs.scrollTop = logs.scrollHeight;
}

async function loadWeibos() {
  const res = await fetch("/api/items?limit=100");
  const data = await res.json();
  if (!data.ok) {
    count.textContent = "数据库读取失败";
    items.innerHTML = emptyCard(data.error || "数据库读取失败");
    return;
  }

  count.textContent = `共 ${data.total || 0} 条，已分析 ${data.analyzed || 0} 条`;
  const list = data.items || [];
  items.innerHTML = list.length ? list.map(renderWeibo).join("") : emptyCard("暂无数据，点击爬取后会在这里展示多平台内容。");
}

async function refreshAll() {
  await Promise.all([loadStatus(), loadWeibos(), checkHealth()]);
}

function renderWeibo(item) {
  const analysis = item.analysis || {};
  const summary = analysis.summary || {};
  const score = Number(summary.total_score);
  const riskLevel = summary.risk_level || statusText(item.analysis_status);
  const reasons = Array.isArray(summary.reasons) ? summary.reasons.slice(0, 5) : [];
  const pics = (item.pics || []).map((pic) => `<img src="${pic.url}" title="${escapeHtml(pic.path)}" loading="lazy">`).join("");
  const matched = Array.isArray(item.matched_keywords) ? item.matched_keywords.join("，") : (item.keyword || "");
  const scoreClass = Number.isFinite(score) ? scoreLevelClass(score) : "pending";
  const platformName = item.platform_name || platformLabel(item.platform);
  const itemId = String(item._id || item.id || "");
  const shouldCollapse = String(item.text || "").length > 140;
  const isExpanded = expandedTextIds.has(itemId);
  const textToggle = shouldCollapse
    ? `<button class="text-toggle" type="button" data-text-toggle="${escapeHtml(itemId)}">${isExpanded ? "收起" : "展开全部"}</button>`
    : "";

  return `
    <article class="weibo">
      <div class="card-head">
        <div>
          <strong>${escapeHtml(item.screen_name || "未知用户")}</strong>
          <div class="meta">
            <span class="platform-chip">${escapeHtml(platformName || "未知平台")}</span>
            <span>${escapeHtml(item.created_at || "")}</span>
            <span>${escapeHtml(item.source || "")}</span>
            <span>命中：${escapeHtml(matched || "无")}</span>
          </div>
        </div>
        <div class="risk ${scoreClass}">
          <span>${escapeHtml(riskLevel || "--")}</span>
          <strong>${Number.isFinite(score) ? score.toFixed(2) : "--"}</strong>
        </div>
      </div>
      <div class="text-block">
        <p class="text${shouldCollapse && !isExpanded ? " is-collapsed" : ""}">${escapeHtml(item.text || "")}</p>
        ${textToggle}
      </div>
      ${pics ? `<div class="pics">${pics}</div>` : ""}
      ${summary.conclusion ? `<p class="conclusion">${escapeHtml(summary.conclusion)}</p>` : ""}
      ${item.analysis_error ? `<p class="error-text">${escapeHtml(item.analysis_error)}</p>` : ""}
      <div class="reason-list">
        ${reasons.length ? reasons.map((reason) => `<span>${escapeHtml(reason)}</span>`).join("") : `<span>${escapeHtml(statusText(item.analysis_status))}</span>`}
      </div>
      ${analysis.final_multimodal_analysis ? renderDetails(item) : ""}
    </article>
  `;
}

function renderDetails(item) {
  const analysis = item.analysis || {};
  const output = analysis.summary?.network_output || {};
  const breakdown = analysis.summary?.modality_breakdown || {};
  const cross = analysis.summary?.cross_modal_features || {};
  const reasons = analysis.summary?.reasons || [];
  const outputRows = Object.entries(output)
    .map(([key, value]) => `<div><span>${escapeHtml(labelFor(key))}</span><strong>${formatScore(value)}</strong></div>`)
    .join("");
  const breakdownRows = Object.entries(breakdown)
    .map(([key, value]) => `<div><span>${escapeHtml(modalityLabel(key))}</span><strong>${formatPercent(value)}</strong></div>`)
    .join("");
  const crossRows = [
    ["semantic_consistency", "语义一致性"],
    ["risk_alignment", "风险类别对齐"],
    ["finance_synergy", "金融主题协同"],
    ["drainage_linkage", "引流联动"],
    ["persuasion_coupling", "诱导耦合"],
  ]
    .filter(([key]) => cross[key] !== undefined)
    .map(([key, label]) => `<div><span>${label}</span><strong>${formatScore(cross[key])}</strong></div>`)
    .join("");
  return `
    <details data-doc-id="${escapeHtml(item._id)}" ${openDetailIds.has(item._id) ? "open" : ""}>
      <summary>查看结构化分析</summary>
      <h3>融合网络输出</h3>
      <div class="detail-grid">${outputRows || "<p>暂无融合网络输出。</p>"}</div>
      <h3>模态权重</h3>
      <div class="detail-grid">${breakdownRows || "<p>暂无模态权重。</p>"}</div>
      <h3>跨模态关键特征</h3>
      <div class="detail-grid">${crossRows || "<p>暂无跨模态特征。</p>"}</div>
      <div class="compact-evidence">
        ${(Array.isArray(reasons) ? reasons.slice(0, 4) : []).map((reason) => `<span>${escapeHtml(reason)}</span>`).join("")}
      </div>
      <a class="report-link" href="/report?id=${encodeURIComponent(item._id)}" target="_blank" rel="noopener">查看完整分析报告</a>
    </details>
  `;
}

items.addEventListener("toggle", (event) => {
  const details = event.target.closest("details[data-doc-id]");
  if (!details) return;
  if (details.open) {
    openDetailIds.add(details.dataset.docId);
  } else {
    openDetailIds.delete(details.dataset.docId);
  }
}, true);

items.addEventListener("click", (event) => {
  const toggle = event.target.closest("button[data-text-toggle]");
  if (!toggle) return;
  const docId = toggle.dataset.textToggle;
  if (!docId) return;
  if (expandedTextIds.has(docId)) {
    expandedTextIds.delete(docId);
  } else {
    expandedTextIds.add(docId);
  }
  loadWeibos();
});

function emptyCard(message) {
  return `<article class="weibo empty"><p>${escapeHtml(message)}</p></article>`;
}

function statusText(status) {
  return {
    done: "已分析",
    error: "分析失败",
    no_image: "无可用配图",
  }[status] || "待分析";
}

function platformLabel(value) {
  return {
    weibo: "微博",
    douyin: "抖音",
    tieba: "百度贴吧",
    xhs: "小红书",
  }[value] || value || "";
}

function scoreLevelClass(score) {
  if (score >= 80) return "high";
  if (score >= 60) return "medium-high";
  if (score >= 40) return "medium";
  return "low";
}

function labelFor(key) {
  return {
    overall_risk: "总体风险",
    financial_risk: "金融风险",
    drainage_risk: "引流风险",
    marketing_risk: "营销诱导",
    consistency_risk: "图文一致性风险",
  }[key] || key;
}

function formatScore(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number.toFixed(2) : "--";
}

function formatPercent(value) {
  const number = Number(value);
  return Number.isFinite(number) ? `${(number * 100).toFixed(1)}%` : "--";
}

function modalityLabel(key) {
  return {
    text: "正文文本",
    image: "图片视觉",
    ocr_text: "OCR 文本",
    cross_modal: "跨模态融合",
  }[key] || key;
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
