const $ = (selector) => document.querySelector(selector);

const params = new URLSearchParams(location.search);
const sourceId = params.get("id") || "";
let application = null;

function sessionHeaders() {
  let session = {};
  try {
    session = JSON.parse(localStorage.getItem("monitorSession") || "{}");
  } catch {
    session = {};
  }
  return {
    "Content-Type": "application/json",
    "X-User-Role": session.role || "user",
    "X-User-Name": session.username || "",
  };
}

async function fetchJson(url, options = {}) {
  const res = await fetch(url, { ...options, headers: { ...sessionHeaders(), ...(options.headers || {}) } });
  const data = await res.json();
  if (!res.ok || data.ok === false) throw new Error(data.error || "请求失败");
  return data;
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]));
}

function readLines(value) {
  return String(value || "").split(/\r?\n|[，,;；\s]+/).map((line) => line.trim()).filter(Boolean).join("\n");
}

async function loadApplication() {
  if (!sourceId) throw new Error("缺少申请 ID");
  const data = await fetchJson(`/api/platform-settings/applications/${encodeURIComponent(sourceId)}`);
  application = data.item;
  render();
}

function render() {
  $("#applicationSubtitle").textContent = `${application.platform_name || "未命名平台"} · ${application.status || "待审核"}`;
  const editable = application.status !== "已通过";
  $("#applicationDetail").innerHTML = `
    <article class="platform-settings-card source-application-card">
      <div class="platform-settings-head">
        <div>
          <h3>${escapeHtml(application.platform_name || "未命名平台")}</h3>
          <p class="platform-settings-note">${escapeHtml(application.platform_type || "未分类")} · ${escapeHtml(application.target_url || "")}</p>
        </div>
        <span class="mini-badge ${application.status === "已退回" ? "pending" : "ok"}">${escapeHtml(application.status || "待审核")}</span>
      </div>
      <div class="source-application-summary">
        <span>提交人：${escapeHtml(application.owner || "")}</span>
        <span>提交时间：${escapeHtml(application.created_at || "")}</span>
        <span>更新时间：${escapeHtml(application.updated_at || "")}</span>
        <span>账号：${escapeHtml(application.account_name || "未填写")}</span>
      </div>
      <div class="config-grid application-review-form polished-review-form">
        <div class="field full"><label>目标网址</label><input value="${escapeHtml(application.target_url || "")}" disabled></div>
        <div class="field full"><label>用户提交关键词</label><textarea disabled>${escapeHtml(application.keywords || "")}</textarea></div>
        <div class="field full"><label>Cookie</label><textarea id="reviewCookie" ${editable ? "" : "disabled"}></textarea></div>
        <div class="field full"><label>接入关键词列表</label><textarea id="reviewKeywords" ${editable ? "" : "disabled"}>${escapeHtml(readLines(application.keywords || ""))}</textarea></div>
        <div class="field"><label>最近天数</label><input id="reviewRecentDays" type="number" min="1" max="3650" value="60" ${editable ? "" : "disabled"}></div>
        <div class="field"><label>最多页数</label><input id="reviewMaxPages" type="number" min="1" max="1000" value="10" ${editable ? "" : "disabled"}></div>
        <div class="field"><label>需要图片</label><div class="toggle-field"><input id="reviewRequireImages" type="checkbox" checked ${editable ? "" : "disabled"}><span>仅保留满足图片要求的内容</span></div></div>
        <div class="field application-actions"><label>审核操作</label><div class="form-actions">
          <button id="approveBtn" type="button" class="primary" ${editable ? "" : "disabled"}>同意并接入</button>
          <button id="rejectBtn" type="button" class="danger-inline" ${editable ? "" : "disabled"}>退回</button>
        </div></div>
      </div>
    </article>`;
  $("#approveBtn")?.addEventListener("click", () => review("approve"));
  $("#rejectBtn")?.addEventListener("click", () => review("reject"));
}

async function review(status) {
  const payload = {
    status,
    platform_config: {
      cookie: $("#reviewCookie").value,
      keywords: $("#reviewKeywords").value,
      recent_days: Number($("#reviewRecentDays").value || 60),
      max_pages: Number($("#reviewMaxPages").value || 10),
      require_images: $("#reviewRequireImages").checked,
    },
  };
  try {
    const data = await fetchJson(`/api/platform-settings/applications/${encodeURIComponent(sourceId)}/review`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    application = data.item;
    render();
    window.alert(status === "approve" ? "已同意并接入平台。" : "已退回申请。");
  } catch (error) {
    window.alert(error.message);
  }
}

loadApplication().catch((error) => {
  $("#applicationSubtitle").textContent = error.message;
  $("#applicationDetail").innerHTML = `<article class="platform-settings-card"><p class="status-empty">${escapeHtml(error.message)}</p></article>`;
});
