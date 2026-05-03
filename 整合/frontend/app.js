const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));

const state = {
  loggedIn: false,
  role: "user",
  user: "",
  displayName: "",
  items: [],
  sources: [],
  status: {},
  health: null,
  platformSettings: { platforms: {}, options: [], known_platforms: [] },
  feedFilter: "all",
  activeView: "home",
  settingsDirty: false,
  activeSettingsPlatformId: "",
  monitorLimit: localStorage.getItem("monitorLimit") || "20",
};

const views = ["home", "collection", "monitor", "risk", "search", "warning", "profile", "admin-platforms", "admin-tasks", "admin-rules", "admin-models", "admin-logs", "admin-users", "admin-settings"];
const adminViews = new Set(views.filter((view) => view.startsWith("admin-")));
const riskTypes = ["虚假宣传风险", "非法集资风险", "金融诈骗风险", "负面舆情风险", "投诉维权风险", "恶意营销风险", "其他风险"];
const sentimentTypes = ["负面", "中性", "正面"];

init();

function init() {
  restoreSession();
  bindEvents();
  applyRole();
  renderStaticAdminPages();
  const initial = state.loggedIn ? (location.hash.replace("#", "") || defaultViewForRole()) : defaultViewForRole();
  switchView(initial);
  if (state.loggedIn) refreshAll();
  setInterval(refreshAll, 10000);
}

function bindEvents() {
  $("#loginForm")?.addEventListener("submit", loginFromForm);
  $("#loginName")?.addEventListener("input", updateLoginButtonState);
  $("#loginPassword")?.addEventListener("input", updateLoginButtonState);
  $("#registerForm")?.addEventListener("submit", registerFromForm);
  $("#showRegisterBtn")?.addEventListener("click", () => switchAuthMode("register"));
  $("#backLoginBtn")?.addEventListener("click", () => switchAuthMode("login"));
  $("#authCloseBtn")?.addEventListener("click", () => {
    $("#authMessage").textContent = "";
  });
  $("#togglePasswordBtn")?.addEventListener("click", () => {
    const input = $("#loginPassword");
    const shouldShow = input.type === "password";
    input.type = shouldShow ? "text" : "password";
    $("#togglePasswordBtn").textContent = shouldShow ? "隐藏密码" : "展示密码";
  });
  $("#logoutBtn")?.addEventListener("click", logout);
  updateLoginButtonState();

  $$(".nav-link[data-view]").forEach((link) => {
    link.addEventListener("click", (event) => {
      event.preventDefault();
      switchView(link.dataset.view);
    });
  });

  $("#refreshBtn")?.addEventListener("click", refreshAll);
  $("#toggleBtn")?.addEventListener("click", toggleCrawl);
  $("#analyzeOldBtn")?.addEventListener("click", analyzeOldItems);
  $("#saveSettingsBtn")?.addEventListener("click", savePlatformSettings);
  $("#sourceForm")?.addEventListener("submit", saveCollectionSource);
  $("#resetSourceBtn")?.addEventListener("click", resetSourceForm);
  $("#profileForm")?.addEventListener("submit", saveProfile);
  $("#passwordForm")?.addEventListener("submit", savePassword);
  $("#searchForm")?.addEventListener("submit", (event) => {
    event.preventDefault();
    renderSearchResults();
  });
  $("#monitorLimitSelect")?.addEventListener("change", (event) => {
    state.monitorLimit = event.target.value;
    localStorage.setItem("monitorLimit", state.monitorLimit);
    renderMonitor();
  });

  $("#sourceTable")?.addEventListener("click", (event) => {
    const edit = event.target.closest("[data-source-edit]");
    const del = event.target.closest("[data-source-delete]");
    if (edit) fillSourceForm(edit.dataset.sourceEdit);
    if (del) deleteCollectionSource(del.dataset.sourceDelete);
  });

  $("#monitorFilters")?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-filter]");
    if (!button) return;
    state.feedFilter = button.dataset.filter;
    $$("#monitorFilters .channel-pill").forEach((pill) => pill.classList.toggle("is-active", pill === button));
    renderMonitor();
  });

  $("#knownPlatformCatalog")?.addEventListener("click", (event) => {
    const addButton = event.target.closest("[data-add-platform]");
    if (addButton) addKnownPlatform(addButton.dataset.addPlatform);
  });

  $("#platformSettingsList")?.addEventListener("input", () => {
    state.settingsDirty = true;
  });

  $("#platformSettingsList")?.addEventListener("click", (event) => {
    const removeButton = event.target.closest("[data-remove-platform]");
    if (removeButton) removeKnownPlatform(removeButton.dataset.removePlatform);
  });

  $("#platformSettingsSelect")?.addEventListener("change", (event) => {
    state.activeSettingsPlatformId = event.target.value;
    renderPlatformSettingsCards();
  });
}

function headers() {
  return { "Content-Type": "application/json", "X-User-Role": state.role, "X-User-Name": state.user };
}

async function fetchJson(url, options = {}) {
  const res = await fetch(url, { ...options, headers: { ...headers(), ...(options.headers || {}) } });
  const data = await res.json();
  if (!res.ok || data.ok === false || data.success === false) throw new Error(data.error || "请求失败");
  return data;
}

async function refreshAll() {
  if (!state.loggedIn) return;
  await Promise.allSettled([loadHealth(), loadStatus(), loadItems(), loadCollectionSources(), loadPlatformSettings()]);
  renderAll();
}

async function loadHealth() {
  try {
    state.health = await fetchJson("/health");
  } catch (error) {
    state.health = { success: false, error: error.message };
  }
}

async function loadStatus() {
  try {
    state.status = await fetchJson("/api/crawl/status");
  } catch (error) {
    state.status = { running: false, logs: [], error: error.message };
  }
}

async function loadItems() {
  try {
    const data = await fetchJson("/api/items?limit=2000");
    state.items = data.items || [];
    state.total = data.total || state.items.length;
  } catch {
    state.items = [];
    state.total = 0;
  }
}

async function loadCollectionSources() {
  try {
    const data = await fetchJson("/api/collection-sources");
    state.sources = data.items || [];
  } catch {
    state.sources = [];
  }
}

async function loadPlatformSettings() {
  if (state.role !== "admin" || state.settingsDirty) return;
  try {
    state.platformSettings = await fetchJson("/api/platform-settings");
  } catch {
    state.platformSettings = { platforms: {}, options: [], known_platforms: [] };
  }
}

function renderAll() {
  renderHealth();
  renderTaskControl();
  renderHome();
  renderCollectionSources();
  renderMonitorFilters();
  renderMonitor();
  renderRiskAnalysis();
  renderWarnings();
  renderSearchResults();
  renderProfile();
  renderAdminStatus();
  renderAdminSettings();
}

function applyRole() {
  document.body.dataset.role = state.role;
  document.body.classList.toggle("is-authenticated", state.loggedIn);
  $$(".admin-only").forEach((el) => el.classList.toggle("is-hidden", state.role !== "admin"));
  $("#currentUserLabel").textContent = state.loggedIn
    ? `${state.displayName || state.user} · ${state.role === "admin" ? "管理员" : "普通用户"}`
    : "未登录";
  renderProfile();
}

function switchView(view) {
  if (!state.loggedIn) {
    state.activeView = defaultViewForRole();
    return;
  }
  const target = views.includes(view) ? view : "home";
  if (adminViews.has(target) && state.role !== "admin") {
    window.alert("普通用户不能访问后台管理功能。");
    return switchView("home");
  }
  state.activeView = target;
  views.forEach((name) => $(`#${name}View`)?.classList.toggle("is-active", name === target));
  $$(".nav-link[data-view]").forEach((link) => link.classList.toggle("is-active", link.dataset.view === target));
  location.hash = target;
}

function restoreSession() {
  try {
    const session = JSON.parse(localStorage.getItem("monitorSession") || "null");
    if (!session?.username || !session?.role) return;
    state.loggedIn = true;
    state.user = session.username;
    state.role = session.role === "admin" ? "admin" : "user";
    state.displayName = session.display_name || session.displayName || session.username;
  } catch {
    localStorage.removeItem("monitorSession");
  }
}

function defaultViewForRole() {
  return state.role === "admin" ? "admin-platforms" : "home";
}

function switchAuthMode(mode) {
  $$(".auth-form").forEach((panel) => panel.classList.toggle("is-active", panel.dataset.authPanel === mode));
  $(".auth-title-tab").textContent = mode === "register" ? "普通用户注册" : "密码登录";
  $("#authMessage").textContent = "";
}

function updateLoginButtonState() {
  const ready = Boolean($("#loginName")?.value.trim() && $("#loginPassword")?.value);
  const button = $("#loginSubmitBtn");
  if (!button) return;
  button.disabled = !ready;
  button.classList.toggle("is-ready", ready);
}

async function loginFromForm(event) {
  event.preventDefault();
  const username = $("#loginName").value;
  const password = $("#loginPassword").value;
  try {
    const data = await postPublicJson("/api/auth/login", { username, password });
    finishLogin(data.user);
  } catch (error) {
    $("#authMessage").textContent = error.message;
  }
}

async function registerFromForm(event) {
  event.preventDefault();
  try {
    const data = await postPublicJson("/api/auth/register", {
      display_name: $("#registerDisplayName").value,
      username: $("#registerName").value,
      password: $("#registerPassword").value,
    });
    finishLogin(data.user);
  } catch (error) {
    $("#authMessage").textContent = error.message;
  }
}

async function postPublicJson(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  if (!res.ok || data.ok === false) throw new Error(data.error || "请求失败");
  return data;
}

function finishLogin(user) {
  state.loggedIn = true;
  state.user = user.username;
  state.role = user.role === "admin" ? "admin" : "user";
  state.displayName = user.display_name || user.username;
  localStorage.setItem("monitorSession", JSON.stringify(user));
  applyRole();
  switchView(defaultViewForRole());
  refreshAll();
}

function logout() {
  localStorage.removeItem("monitorSession");
  state.loggedIn = false;
  state.role = "user";
  state.user = "";
  state.displayName = "";
  applyRole();
  location.hash = "";
}

function renderHealth() {
  const pill = $("#healthStatus");
  const ok = state.health?.success;
  const fallbackCount = Object.values(state.health?.component_status || {}).filter((value) => value !== "model").length;
  pill.textContent = ok ? (fallbackCount ? `降级运行，${fallbackCount} 个组件兜底` : "模型引擎就绪") : (state.health?.error || "后端未连接");
  pill.className = ok ? (fallbackCount ? "status-pill warn" : "status-pill ok") : "status-pill error";
}

function renderTaskControl() {
  const status = state.status || {};
  $("#runState").textContent = status.running ? (status.paused ? "已暂停" : "采集中") : "空闲";
  $("#runState").className = status.running ? (status.paused ? "badge paused" : "badge") : "badge idle";
  $("#toggleBtn").textContent = status.running && !status.paused ? "暂停" : "启动采集";
  const stats = status.current_stats || status.last_result || {};
  $("#lastResult").textContent = `写入 ${stats.inserted || 0}，重复 ${stats.skipped || 0}，未命中 ${stats.unmatched || 0}，丢弃 ${stats.discarded || 0}`;
  $("#lastError").textContent = status.last_error ? `错误：${status.last_error}` : "";
  $("#logsPanel").textContent = status.logs?.length ? status.logs.join("\n") : "等待爬取任务启动...";
  $("#logsMeta").textContent = status.running ? `最近 ${status.logs?.length || 0} 条日志` : "当前没有运行任务";
  $("#platformSelector").innerHTML = (state.platformSettings.options || []).map((option) => `
    <label class="${option.available ? "" : "is-pending"}">
      <input type="checkbox" name="platform" value="${escapeHtml(option.id)}" ${option.selected ? "checked" : ""} ${option.available ? "" : "disabled"}>
      ${escapeHtml(option.label)}
    </label>
  `).join("");
}

async function toggleCrawl() {
  try {
    const selected = $$("input[name='platform']:checked").map((input) => input.value);
    if (state.status.running && !state.status.paused) {
      await fetchJson("/api/crawl/pause", { method: "POST", body: "{}" });
    } else {
      await fetchJson("/api/crawl/start", { method: "POST", body: JSON.stringify({ platforms: selected }) });
    }
    await refreshAll();
  } catch (error) {
    window.alert(error.message);
  }
}

async function analyzeOldItems() {
  try {
    const data = await fetchJson("/api/analyze/unprocessed?limit=20", { method: "POST", body: "{}" });
    window.alert(`已处理 ${data.processed || 0} 条历史数据。`);
    await refreshAll();
  } catch (error) {
    window.alert(error.message);
  }
}

function renderHome() {
  const highRisk = highRiskItems();
  const platforms = new Set(state.items.map((item) => item.platform).filter(Boolean));
  $("#overviewCards").innerHTML = [
    ["总舆情数量", state.total || state.items.length],
    ["今日新增", countToday(state.items)],
    ["高风险舆情", highRisk.length],
    ["涉及平台", platforms.size],
  ].map(([label, value]) => `<article class="overview-card"><span>${label}</span><strong>${value}</strong></article>`).join("");
  $("#riskDistribution").innerHTML = renderBars(countBy(state.items, riskBucket), state.total || state.items.length || 1);
  $("#platformDistribution").innerHTML = renderBars(countBy(state.items, (item) => platformLabel(item.platform)), state.total || state.items.length || 1);
  $("#homeMeta").textContent = `展示 ${Math.min(6, highRisk.length)} 条`;
  $("#homeHighRiskItems").innerHTML = renderCompactRows(highRisk.slice(0, 6));
}

function renderMonitorFilters() {
  const filters = [
    ["all", "全部"], ["weibo", "微博"], ["douyin", "抖音"], ["tieba", "贴吧"], ["xhs", "小红书"], ["high", "高风险"], ["recent", "近两个月"],
  ];
  $("#monitorFilters").innerHTML = filters.map(([id, label]) => `<button class="channel-pill ${state.feedFilter === id ? "is-active" : ""}" type="button" data-filter="${id}">${label}</button>`).join("");
}

function renderMonitor() {
  const list = filteredItems();
  const visible = limitedMonitorItems(list);
  if ($("#monitorLimitSelect")) $("#monitorLimitSelect").value = state.monitorLimit;
  $("#count").textContent = `共 ${state.total || 0} 条，筛选 ${list.length} 条，当前展示 ${visible.length} 条`;
  $("#items").innerHTML = visible.length ? visible.map(renderItem).join("") : emptyCard("当前没有符合条件的舆情数据。");
}

function renderRiskAnalysis() {
  $("#riskTypeChart").innerHTML = renderBars(countBy(state.items, inferRiskType), state.total || state.items.length || 1);
  $("#sentimentChart").innerHTML = renderBars(countBy(state.items, inferSentiment), state.total || state.items.length || 1);
  const list = highRiskItems();
  $("#riskMeta").textContent = `按总舆情 ${state.total || state.items.length || 0} 条分析，高风险 ${list.length} 条`;
  $("#riskItems").innerHTML = list.length ? list.slice(0, 10).map(renderItem).join("") : emptyCard("当前暂无高风险分析结果。");
}

function renderWarnings() {
  const list = highRiskItems();
  $("#warningMeta").textContent = `预警 ${list.length} 条`;
  $("#warningItems").innerHTML = list.length ? `
    <table><thead><tr><th>等级</th><th>平台</th><th>预警内容</th><th>时间</th><th>状态</th><th>操作</th></tr></thead><tbody>
      ${list.map((item) => `<tr><td>${riskBucket(item)}</td><td>${platformLabel(item.platform)}</td><td>${escapeHtml(shortText(item.text, 72))}</td><td>${escapeHtml(item.created_at || "")}</td><td>待处理</td><td><a href="/report?id=${encodeURIComponent(item._id)}" target="_blank">详情</a></td></tr>`).join("")}
    </tbody></table>` : emptyTable("当前暂无预警。");
}

function renderProfile() {
  if (!$("#profileUsername")) return;
  $("#profileUsername").value = state.user || "";
  $("#profileDisplayName").value = state.displayName || "";
  $("#profileRoleMeta").textContent = state.role === "admin" ? "管理员账号" : "普通用户账号";
}

async function saveProfile(event) {
  event.preventDefault();
  const message = $("#profileMessage");
  message.textContent = "";
  try {
    const data = await fetchJson("/api/account/profile", {
      method: "PUT",
      body: JSON.stringify({ display_name: $("#profileDisplayName").value }),
    });
    state.displayName = data.user.display_name;
    localStorage.setItem(
      "monitorSession",
      JSON.stringify({ username: state.user, role: state.role, display_name: state.displayName }),
    );
    applyRole();
    message.textContent = "个人资料已保存。";
    message.className = "form-message ok";
  } catch (error) {
    message.textContent = error.message;
    message.className = "form-message error";
  }
}

async function savePassword(event) {
  event.preventDefault();
  const message = $("#passwordMessage");
  message.textContent = "";
  const oldPassword = $("#oldPassword").value;
  const newPassword = $("#newPassword").value;
  const confirmPassword = $("#confirmPassword").value;
  if (newPassword !== confirmPassword) {
    message.textContent = "两次输入的新密码不一致。";
    message.className = "form-message error";
    return;
  }
  try {
    await fetchJson("/api/account/password", {
      method: "PUT",
      body: JSON.stringify({ old_password: oldPassword, new_password: newPassword }),
    });
    $("#passwordForm").reset();
    message.textContent = "密码已修改，下次登录请使用新密码。";
    message.className = "form-message ok";
  } catch (error) {
    message.textContent = error.message;
    message.className = "form-message error";
  }
}

function renderSearchResults() {
  const keyword = ($("#searchKeyword")?.value || "").trim();
  const platform = $("#searchPlatform")?.value || "";
  const risk = $("#searchRisk")?.value || "";
  const sentiment = $("#searchSentiment")?.value || "";
  const list = state.items.filter((item) => {
    if (keyword && !(`${item.text || ""} ${item.keyword || ""}`.includes(keyword))) return false;
    if (platform && item.platform !== platform) return false;
    if (risk && !riskBucket(item).includes({ high: "高", medium: "中", low: "低" }[risk])) return false;
    if (sentiment && inferSentiment(item) !== sentiment) return false;
    return true;
  });
  $("#searchMeta").textContent = `在总舆情 ${state.total || state.items.length || 0} 条中找到 ${list.length} 条`;
  $("#searchResults").innerHTML = list.length ? list.map(renderItem).join("") : emptyCard("没有找到符合条件的舆情。");
}

function renderCollectionSources() {
  $("#sourceMeta").textContent = `${state.role === "admin" ? "全部" : "我的"}采集源 ${state.sources.length} 个`;
  $("#sourceTable").innerHTML = state.sources.length ? `
    <table><thead><tr><th>平台名称</th><th>类型</th><th>网址</th><th>关键词</th><th>状态</th><th>提交人</th><th>操作</th></tr></thead><tbody>
      ${state.sources.map((item) => `<tr>
        <td>${escapeHtml(item.platform_name)}</td><td>${escapeHtml(item.platform_type)}</td><td>${escapeHtml(shortText(item.target_url, 34))}</td>
        <td>${escapeHtml(shortText(item.keywords, 30))}</td><td>${escapeHtml(item.status)}</td><td>${escapeHtml(ownerLabel(item.owner))}</td>
        <td><button type="button" data-source-edit="${escapeHtml(item.id)}">编辑</button><button type="button" class="danger-inline" data-source-delete="${escapeHtml(item.id)}">删除</button></td>
      </tr>`).join("")}
    </tbody></table>` : emptyTable("还没有采集源，请先提交采集需求。");
}

async function saveCollectionSource(event) {
  event.preventDefault();
  const id = $("#sourceId").value;
  const payload = {
    platform_name: $("#sourcePlatformName").value,
    target_url: $("#sourceTargetUrl").value,
    account_name: $("#sourceAccountName").value,
    platform_type: $("#sourcePlatformType").value,
    time_range: $("#sourceTimeRange").value,
    keywords: $("#sourceKeywords").value,
  };
  try {
    await fetchJson(id ? `/api/collection-sources/${encodeURIComponent(id)}` : "/api/collection-sources", {
      method: id ? "PUT" : "POST",
      body: JSON.stringify(payload),
    });
    resetSourceForm();
    await loadCollectionSources();
    renderCollectionSources();
  } catch (error) {
    window.alert(error.message);
  }
}

function fillSourceForm(id) {
  const item = state.sources.find((entry) => entry.id === id);
  if (!item) return;
  $("#sourceId").value = item.id;
  $("#sourcePlatformName").value = item.platform_name || "";
  $("#sourceTargetUrl").value = item.target_url || "";
  $("#sourceAccountName").value = item.account_name || "";
  $("#sourcePlatformType").value = item.platform_type || "新闻网站";
  $("#sourceTimeRange").value = item.time_range || "近两个月";
  $("#sourceKeywords").value = item.keywords || "";
  switchView("collection");
}

async function deleteCollectionSource(id) {
  if (!window.confirm("确定删除这个采集源吗？")) return;
  try {
    await fetchJson(`/api/collection-sources/${encodeURIComponent(id)}`, { method: "DELETE" });
    await loadCollectionSources();
    renderCollectionSources();
  } catch (error) {
    window.alert(error.message);
  }
}

function resetSourceForm() {
  $("#sourceForm").reset();
  $("#sourceId").value = "";
}

function renderAdminStatus() {
  $("#taskMeta").textContent = state.status.running ? "任务运行中" : "任务空闲";
  $("#taskSummaryList").innerHTML = [
    ["运行状态", state.status.running ? (state.status.paused ? "已暂停" : "运行中") : "空闲"],
    ["平台数量", (state.status.selected_platforms || []).length || 0],
    ["累计写入", state.status.current_stats?.inserted || 0],
    ["累计重复", state.status.current_stats?.skipped || 0],
    ["未命中", state.status.current_stats?.unmatched || 0],
    ["丢弃", state.status.current_stats?.discarded || 0],
  ].map(([label, value]) => `<div class="component-row"><span>${label}</span><strong>${value}</strong></div>`).join("");
  $("#engineStatusText").textContent = state.health?.model_ready ? "已加载" : "待初始化";
  $("#healthStatusMirror").textContent = state.health?.success ? "在线" : "异常";
  $("#statusMeta").textContent = state.health?.success ? `组件 ${Object.keys(state.health.component_status || {}).length} 项` : "状态异常";
  $("#componentStatusList").innerHTML = Object.entries(state.health?.component_status || {}).map(([name, status]) => `<div class="component-row"><span>${escapeHtml(name)}</span><strong>${escapeHtml(status)}</strong></div>`).join("") || `<p class="status-empty">暂无组件状态。</p>`;
}

function renderAdminSettings() {
  if (state.role !== "admin") return;
  renderKnownPlatformCatalog();
  renderPlatformSettingsCards();
}

function renderKnownPlatformCatalog() {
  $("#knownPlatformCatalog").innerHTML = (state.platformSettings.known_platforms || []).map((platform) => `
    <article class="catalog-item"><div><h4>${escapeHtml(platform.label)}</h4><p>${escapeHtml(platform.description || "")}</p></div><button type="button" data-add-platform="${escapeHtml(platform.id)}">${platform.added ? "撤销加入" : "加入设置"}</button></article>
  `).join("") || emptyCard("暂无可扩展平台。");
}

function renderPlatformSettingsCards() {
  const entries = Object.values(state.platformSettings.platforms || {});
  $("#settingsStatusText").textContent = `当前共 ${entries.length} 个平台配置`;
  if (!entries.length) {
    $("#platformSettingsList").innerHTML = emptyCard("暂无平台配置。");
    return;
  }
  if (!entries.some((item) => item.id === state.activeSettingsPlatformId)) state.activeSettingsPlatformId = entries[0].id;
  $("#platformSettingsSelect").innerHTML = entries.map((item) => `<option value="${escapeHtml(item.id)}" ${item.id === state.activeSettingsPlatformId ? "selected" : ""}>${escapeHtml(item.label)}</option>`).join("");
  const config = entries.find((item) => item.id === state.activeSettingsPlatformId) || entries[0];
  $("#platformSettingsList").innerHTML = `
    <article class="platform-settings-card">
      <div class="platform-settings-head"><div><h3>${escapeHtml(config.label)}</h3><p class="platform-settings-note">${escapeHtml(config.description || "")}</p></div><span class="mini-badge ${config.available ? "ok" : "pending"}">${config.available ? "已接入" : "待接入"}</span></div>
      <div class="config-grid">
        <div class="field"><label>默认参与爬取</label><div class="toggle-field"><input type="checkbox" data-setting="${escapeHtml(config.id)}" data-field="selected" ${config.selected ? "checked" : ""} ${config.available ? "" : "disabled"}><span>任务启动时默认勾选</span></div></div>
        <div class="field"><label>需要图片</label><div class="toggle-field"><input type="checkbox" data-setting="${escapeHtml(config.id)}" data-field="require_images" ${config.require_images ? "checked" : ""}><span>仅保留满足图片要求的内容</span></div></div>
        <div class="field full"><label>Cookie</label><textarea data-setting="${escapeHtml(config.id)}" data-field="cookie">${escapeHtml(config.cookie || "")}</textarea></div>
        <div class="field full"><label>关键词列表</label><textarea data-setting="${escapeHtml(config.id)}" data-field="keywords">${escapeHtml((config.keywords || []).join("\n"))}</textarea></div>
        <div class="field"><label>每个关键词最多页数</label><input type="number" min="1" max="1000" data-setting="${escapeHtml(config.id)}" data-field="max_pages" value="${escapeHtml(config.max_pages || 10)}"></div>
      </div>
    </article>`;
}

async function savePlatformSettings() {
  const payload = { added_platforms: [], platforms: {} };
  Object.values(state.platformSettings.platforms || {}).forEach((config) => {
    payload.platforms[config.id] = {
      selected: readSetting(config.id, "selected", "checkbox", config.selected),
      require_images: readSetting(config.id, "require_images", "checkbox", config.require_images),
      cookie: readSetting(config.id, "cookie", "text", config.cookie || ""),
      keywords: readLines(config.id, "keywords"),
      max_pages: Number(readSetting(config.id, "max_pages", "number", config.max_pages || 10)),
    };
  });
  payload.added_platforms = (state.platformSettings.known_platforms || []).filter((item) => item.added).map((item) => item.id);
  try {
    state.platformSettings = await fetchJson("/api/platform-settings", { method: "POST", body: JSON.stringify(payload) });
    state.settingsDirty = false;
    renderAdminSettings();
    window.alert("平台配置已保存。");
  } catch (error) {
    window.alert(error.message);
  }
}

function addKnownPlatform(id) {
  state.settingsDirty = true;
  state.platformSettings.known_platforms = (state.platformSettings.known_platforms || []).map((item) => item.id === id ? { ...item, added: !item.added } : item);
  const info = state.platformSettings.known_platforms.find((item) => item.id === id);
  if (info?.added) {
    state.platformSettings.platforms[id] = state.platformSettings.platforms[id] || { id, label: info.label, description: info.description, available: false, added: true, selected: false, keywords: [], cookie: "", max_pages: 10, require_images: true };
    state.activeSettingsPlatformId = id;
  } else {
    delete state.platformSettings.platforms[id];
  }
  renderAdminSettings();
}

function removeKnownPlatform(id) {
  addKnownPlatform(id);
}

function readSetting(id, field, type, fallback) {
  const el = document.querySelector(`[data-setting="${id}"][data-field="${field}"]`);
  if (!el) return fallback;
  return type === "checkbox" ? el.checked : el.value;
}

function readLines(id, field) {
  return String(readSetting(id, field, "text", "") || "").split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
}

function renderStaticAdminPages() {
  $("#ruleCards").innerHTML = ["平台适配规则", "关键词规则", "抓取字段", "反爬策略参数", "采集频率", "数据清洗规则"].map((title) => `<article class="admin-card"><h3>${title}</h3><p>该项由管理员在后台维护，普通用户前台不可见。</p></article>`).join("");
  $("#permissionMatrix").innerHTML = `<table><thead><tr><th>角色</th><th>前台业务功能</th><th>后台管理功能</th><th>采集源权限</th></tr></thead><tbody><tr><td>普通用户</td><td>首页、数据采集、舆情监测、风险分析、检索、预警</td><td>无权限</td><td>只能维护自己提交的采集源</td></tr><tr><td>管理员</td><td>全部前台功能</td><td>平台、任务、规则、模型、日志、用户、系统设置</td><td>可维护全部采集源和监测任务</td></tr></tbody></table>`;
  $("#systemSettings").innerHTML = ["基础参数配置", "系统字典配置", "风险等级规则", "预警阈值配置", "数据存储配置"].map((title) => `<article class="admin-card"><h3>${title}</h3><p>用于系统维护和验收演示，入口仅管理员可见。</p></article>`).join("");
}

function filteredItems() {
  return state.items.filter((item) => {
    if (["weibo", "douyin", "tieba", "xhs"].includes(state.feedFilter)) return item.platform === state.feedFilter;
    if (state.feedFilter === "high") return riskScore(item) >= 80;
    if (state.feedFilter === "recent") return isWithinRecentDays(item.created_at, 60);
    return true;
  });
}

function limitedMonitorItems(list) {
  if (state.monitorLimit === "all") return list;
  const limit = Number(state.monitorLimit);
  return Number.isFinite(limit) ? list.slice(0, limit) : list;
}

function highRiskItems() {
  return state.items.filter((item) => riskScore(item) >= 80).slice().sort((a, b) => riskScore(b) - riskScore(a));
}

function renderItem(item) {
  const score = riskScore(item);
  const reasons = item.analysis?.summary?.reasons || [];
  return `<article class="weibo">
    <div class="card-head"><div class="user-head"><span class="avatar">${escapeHtml(getAvatarText(item.screen_name))}</span><div class="user-copy"><strong>${escapeHtml(item.screen_name || "未知用户")}</strong></div></div><div><div class="meta"><span class="platform-chip">${platformLabel(item.platform)}</span><span>${escapeHtml(item.created_at || "")}</span><span>情感：${inferSentiment(item)}</span><span>${inferRiskType(item)}</span></div></div><div class="risk ${scoreLevelClass(score)}"><span>${riskBucket(item)}</span><strong>${Number.isFinite(score) ? score.toFixed(1) : "--"}</strong></div></div>
    <p class="text">${escapeHtml(item.text || "")}</p>
    <div class="reason-list">${reasons.length ? reasons.slice(0, 4).map((reason) => `<span>${escapeHtml(reason)}</span>`).join("") : `<span>${escapeHtml(item.analysis_status || "待分析")}</span>`}</div>
    <a class="report-link" href="/report?id=${encodeURIComponent(item._id)}" target="_blank">查看详情</a>
  </article>`;
}

function renderCompactRows(list) {
  return list.length ? `<table><thead><tr><th>平台</th><th>内容摘要</th><th>风险等级</th><th>时间</th></tr></thead><tbody>${list.map((item) => `<tr><td>${platformLabel(item.platform)}</td><td>${escapeHtml(shortText(item.text, 80))}</td><td>${riskBucket(item)}</td><td>${escapeHtml(item.created_at || "")}</td></tr>`).join("")}</tbody></table>` : emptyTable("当前暂无高风险舆情。");
}

function renderBars(counts, total) {
  const entries = Object.entries(counts).sort((a, b) => b[1] - a[1]);
  return entries.length ? entries.map(([label, value]) => `<div class="bar-row"><div class="bar-head"><span>${escapeHtml(label)}</span><strong>${value}</strong></div><div class="bar-track"><div class="bar-fill" style="width:${Math.max(4, value / total * 100)}%"></div></div></div>`).join("") : "<p class='status-empty'>暂无统计数据。</p>";
}

function countBy(list, picker) {
  return list.reduce((acc, item) => {
    const key = picker(item) || "未知";
    acc[key] = (acc[key] || 0) + 1;
    return acc;
  }, {});
}

function countToday(list) {
  const today = new Date().toISOString().slice(0, 10);
  return list.filter((item) => String(item.created_at || "").startsWith(today)).length;
}

function riskScore(item) {
  return Number(item.analysis?.summary?.total_score ?? NaN);
}

function riskBucket(item) {
  const score = riskScore(item);
  if (score >= 80) return "高风险";
  if (score >= 60) return "中高风险";
  if (score >= 40) return "中风险";
  if (Number.isFinite(score)) return "低风险";
  return "待分析";
}

function inferRiskType(item) {
  const text = `${item.text || ""} ${(item.analysis?.summary?.reasons || []).join(" ")}`;
  if (/集资|返利|资金盘/.test(text)) return "非法集资风险";
  if (/诈骗|套路|骗/.test(text)) return "金融诈骗风险";
  if (/维权|投诉|暴雷|爆雷/.test(text)) return "投诉维权风险";
  if (/稳赚|保本|高收益|诱导/.test(text)) return "虚假宣传风险";
  if (/营销|引流|私信|加群/.test(text)) return "恶意营销风险";
  if (/负面|风险|舆情/.test(text)) return "负面舆情风险";
  return riskTypes[Math.abs(hashCode(item._id || item.id || item.text || "")) % riskTypes.length];
}

function inferSentiment(item) {
  const score = riskScore(item);
  if (score >= 60) return "负面";
  if (score >= 40) return "中性";
  if (Number.isFinite(score)) return "正面";
  return sentimentTypes[Math.abs(hashCode(item._id || item.id || "")) % sentimentTypes.length];
}

function scoreLevelClass(score) {
  if (score >= 80) return "high";
  if (score >= 60) return "medium-high";
  if (score >= 40) return "medium";
  return "low";
}

function platformLabel(value) {
  return { weibo: "微博", douyin: "抖音", tieba: "百度贴吧", xhs: "小红书" }[value] || value || "未知平台";
}

function ownerLabel(value) {
  return { "business-user": "业务用户", admin: "管理员" }[value] || value || "";
}

function isWithinRecentDays(value, days) {
  const time = Date.parse(String(value || "").replace(/\./g, "-").replace(/\//g, "-").replace(" ", "T"));
  return Number.isFinite(time) && Date.now() - time <= days * 86400000;
}

function shortText(value, max) {
  const text = String(value || "");
  return text.length > max ? `${text.slice(0, max)}...` : text;
}

function getAvatarText(name) {
  return Array.from(String(name || "匿").trim())[0] || "匿";
}

function hashCode(value) {
  return Array.from(String(value)).reduce((hash, char) => ((hash << 5) - hash + char.charCodeAt(0)) | 0, 0);
}

function emptyCard(message) {
  return `<article class="weibo empty"><p>${escapeHtml(message)}</p></article>`;
}

function emptyTable(message) {
  return `<div class="empty-table">${escapeHtml(message)}</div>`;
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" }[char]));
}
