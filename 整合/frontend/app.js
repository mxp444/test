const toggleBtn = document.querySelector("#toggleBtn");
const refreshBtn = document.querySelector("#refreshBtn");
const analyzeOldBtn = document.querySelector("#analyzeOldBtn");
const saveSettingsBtn = document.querySelector("#saveSettingsBtn");
const runState = document.querySelector("#runState");
const lastResult = document.querySelector("#lastResult");
const lastError = document.querySelector("#lastError");
const logs = document.querySelector("#logsPanel");
const logsMeta = document.querySelector("#logsMeta");
const count = document.querySelector("#count");
const items = document.querySelector("#items");
const watchCount = document.querySelector("#watchCount");
const watchItems = document.querySelector("#watchItems");
const healthStatus = document.querySelector("#healthStatus");
const healthStatusMirror = document.querySelector("#healthStatusMirror");
const runStateMirror = document.querySelector("#runStateMirror");
const engineStatusText = document.querySelector("#engineStatusText");
const selectedPlatformsText = document.querySelector("#selectedPlatformsText");
const statusMeta = document.querySelector("#statusMeta");
const componentStatusList = document.querySelector("#componentStatusList");
const taskSummaryList = document.querySelector("#taskSummaryList");
const initErrorsList = document.querySelector("#initErrorsList");
const metricInserted = document.querySelector("#metricInserted");
const metricSkipped = document.querySelector("#metricSkipped");
const metricUnmatched = document.querySelector("#metricUnmatched");
const metricDiscarded = document.querySelector("#metricDiscarded");
const platformSelector = document.querySelector("#platformSelector");
const channelPills = Array.from(document.querySelectorAll(".channel-pill"));
const navLinks = Array.from(document.querySelectorAll(".nav-link[data-view], .nav-link[data-scroll]"));
const homeView = document.querySelector("#homeView");
const settingsView = document.querySelector("#settingsView");
const watchView = document.querySelector("#watchView");
const logsView = document.querySelector("#logsView");
const statusView = document.querySelector("#statusView");
const knownPlatformCatalog = document.querySelector("#knownPlatformCatalog");
const platformSettingsList = document.querySelector("#platformSettingsList");
const settingsStatusText = document.querySelector("#settingsStatusText");
const platformSettingsSelect = document.querySelector("#platformSettingsSelect");

let currentStatus = { running: false, paused: false };
let currentHealth = null;
let platformInputs = [];
let platformSettingsState = { platforms: {}, options: [], known_platforms: [] };
let currentFeedFilter = "all";
let cachedItems = [];
let cachedWatchItems = [];
let settingsDirty = false;
let activeSettingsPlatformId = "";
const openDetailIds = new Set();
const expandedTextIds = new Set();

bindEvents();
checkHealth();
refreshAll();
setInterval(refreshAll, 10000);

function bindEvents() {
  toggleBtn.addEventListener("click", toggleCrawl);
  refreshBtn.addEventListener("click", refreshAll);
  analyzeOldBtn.addEventListener("click", analyzeOldItems);
  if (saveSettingsBtn) saveSettingsBtn.addEventListener("click", savePlatformSettings);

  channelPills.forEach((button) => {
    button.addEventListener("click", () => {
      currentFeedFilter = button.dataset.filter || "all";
      channelPills.forEach((pill) => pill.classList.toggle("is-active", pill === button));
      renderItemList(cachedItems);
    });
  });

  navLinks.forEach((link) => {
    link.addEventListener("click", (event) => {
      const view = link.dataset.view;
      const scrollTarget = link.dataset.scroll;
      if (view) {
        event.preventDefault();
        switchView(view);
      } else if (scrollTarget) {
        event.preventDefault();
        document.getElementById(scrollTarget)?.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    });
  });

  items.addEventListener(
    "toggle",
    (event) => {
      const details = event.target.closest("details[data-doc-id]");
      if (!details) return;
      if (details.open) {
        openDetailIds.add(details.dataset.docId);
      } else {
        openDetailIds.delete(details.dataset.docId);
      }
    },
    true,
  );

  items.addEventListener("click", (event) => {
    const textToggle = event.target.closest("button[data-text-toggle]");
    if (textToggle) {
      const docId = textToggle.dataset.textToggle;
      if (docId) {
        if (expandedTextIds.has(docId)) {
          expandedTextIds.delete(docId);
        } else {
          expandedTextIds.add(docId);
        }
        renderItemList(cachedItems);
      }
      return;
    }

    const watchButton = event.target.closest("button[data-watch-add]");
    if (watchButton) {
      addToWatchlist(watchButton.dataset.watchAdd);
    }
  });

  watchItems?.addEventListener("click", (event) => {
    const removeButton = event.target.closest("button[data-watch-remove]");
    if (removeButton) {
      removeFromWatchlist(removeButton.dataset.watchRemove);
      return;
    }

    const textToggle = event.target.closest("button[data-text-toggle]");
    if (textToggle) {
      const docId = textToggle.dataset.textToggle;
      if (docId) {
        if (expandedTextIds.has(docId)) {
          expandedTextIds.delete(docId);
        } else {
          expandedTextIds.add(docId);
        }
        renderWatchlist(cachedWatchItems);
      }
    }
  });

  knownPlatformCatalog?.addEventListener("click", (event) => {
    const addButton = event.target.closest("button[data-add-platform]");
    if (addButton) addKnownPlatform(addButton.dataset.addPlatform);
  });

  platformSettingsList?.addEventListener("click", (event) => {
    const removeButton = event.target.closest("button[data-remove-platform]");
    if (removeButton) removeKnownPlatform(removeButton.dataset.removePlatform);
  });

  platformSettingsList?.addEventListener("input", () => {
    settingsDirty = true;
  });

  platformSettingsSelect?.addEventListener("change", () => {
    activeSettingsPlatformId = platformSettingsSelect.value;
    renderPlatformSettingsCards(platformSettingsState.platforms || {});
  });
}

function switchView(view) {
  const isSettings = view === "settings";
  const isWatch = view === "watch";
  const isLogs = view === "logs";
  const isStatus = view === "status";
  homeView.classList.toggle("is-active", !isSettings && !isWatch && !isLogs && !isStatus);
  settingsView.classList.toggle("is-active", isSettings);
  watchView.classList.toggle("is-active", isWatch);
  logsView.classList.toggle("is-active", isLogs);
  statusView.classList.toggle("is-active", isStatus);
  navLinks.forEach((link) => {
    if (!link.dataset.view) return;
    link.classList.toggle("is-active", link.dataset.view === view);
  });
}

async function checkHealth() {
  try {
    const response = await fetch("/health");
    const payload = await response.json();
    if (!response.ok || !payload.success) throw new Error(payload.error || "后端服务异常");
    currentHealth = payload;
    const fallbackCount = Object.values(payload.component_status || {}).filter((value) => value !== "model").length;
    healthStatus.textContent = fallbackCount
      ? `模型就绪，${fallbackCount} 个组件使用兜底`
      : "模型引擎就绪";
    healthStatus.className = fallbackCount ? "status-pill warn" : "status-pill ok";
    if (healthStatusMirror) healthStatusMirror.textContent = fallbackCount ? "降级运行" : "在线";
    renderSystemStatus();
  } catch (error) {
    currentHealth = { success: false, error: error.message || "后端服务未连接" };
    healthStatus.textContent = error.message || "后端服务未连接";
    healthStatus.className = "status-pill error";
    if (healthStatusMirror) healthStatusMirror.textContent = "异常";
    renderSystemStatus();
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
  const values = platformInputs.filter((input) => input.checked && !input.disabled).map((input) => input.value);
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
    await loadItems();
    window.alert(`已处理 ${data.processed || 0} 条历史数据。`);
  } catch (error) {
    window.alert(error.message);
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
    if (runStateMirror) runStateMirror.textContent = "暂停";
  } else if (status.running) {
    runState.textContent = "爬取与分析中";
    runState.className = "badge";
    toggleBtn.textContent = "暂停";
    toggleBtn.className = "warning";
    if (runStateMirror) runStateMirror.textContent = "运行中";
  } else {
    runState.textContent = "空闲";
    runState.className = "badge idle";
    toggleBtn.textContent = "爬取";
    toggleBtn.className = "primary";
    if (runStateMirror) runStateMirror.textContent = "空闲";
  }

  const stats = status.current_stats || status.last_result || {};
  platformInputs.forEach((input) => {
    input.disabled = Boolean(status.running) || input.dataset.available === "false";
    if (status.running) {
      input.checked = (status.selected_platforms || []).includes(input.value);
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
  if (logsMeta) {
    logsMeta.textContent = status.running
      ? `当前展示最近 ${status.logs?.length || 0} 条日志`
      : "当前没有运行中的任务";
  }
  renderSystemStatus();
}

async function loadItems() {
  const res = await fetch("/api/items?limit=100");
  const data = await res.json();
  if (!data.ok) {
    count.textContent = "数据库读取失败";
    items.innerHTML = emptyCard(data.error || "数据库读取失败");
    return;
  }
  cachedItems = data.items || [];
  renderItemList(cachedItems, data.total || 0, data.analyzed || 0);
}

async function loadWatchlist() {
  const res = await fetch("/api/watchlist?limit=100");
  const data = await res.json();
  if (!data.ok) {
    watchCount.textContent = "读取失败";
    watchItems.innerHTML = emptyCard(data.error || "追踪观测读取失败");
    return;
  }
  cachedWatchItems = data.items || [];
  renderWatchlist(cachedWatchItems, data.total || 0);
}

async function loadPlatformSettings(force = false) {
  if (!force && settingsDirty && settingsView.classList.contains("is-active")) return;
  const res = await fetch("/api/platform-settings");
  const data = await res.json();
  if (!data.ok) throw new Error("平台设置读取失败");
  platformSettingsState = data;
  settingsDirty = false;
  renderPlatformSelector(data.options || []);
  renderKnownPlatformCatalog(data.known_platforms || []);
  renderPlatformSettingsCards(data.platforms || {});
}

async function refreshAll() {
  try {
    await Promise.all([loadPlatformSettings(), loadStatus(), loadItems(), loadWatchlist(), checkHealth()]);
  } catch (error) {
    console.error(error);
  }
}

function renderPlatformSelector(options) {
  platformSelector.innerHTML = options
    .map((option) => {
      const disabled = !option.available;
      return `
        <label class="${disabled ? "is-pending" : ""}">
          <input
            type="checkbox"
            name="platform"
            value="${escapeHtml(option.id)}"
            data-available="${option.available ? "true" : "false"}"
            ${option.selected ? "checked" : ""}
            ${disabled ? "disabled" : ""}
          >
          ${escapeHtml(option.label)}
        </label>
      `;
    })
    .join("");
  platformInputs = Array.from(platformSelector.querySelectorAll("input[name='platform']"));
}

function renderKnownPlatformCatalog(platforms) {
  knownPlatformCatalog.innerHTML = platforms
    .map((platform) => `
      <article class="catalog-item">
        <div>
          <h4>${escapeHtml(platform.label)}</h4>
          <p>${escapeHtml(platform.description || "")}</p>
        </div>
        <button
          class="${platform.added ? "secondary" : ""}"
          type="button"
          data-add-platform="${escapeHtml(platform.id)}"
        >${platform.added ? "撤销加入" : "加入设置"}</button>
      </article>
    `)
    .join("");
}

function renderPlatformSettingsCards(platforms) {
  const entries = Object.values(platforms);
  settingsStatusText.textContent = `当前共 ${entries.length} 个平台配置`;
  renderPlatformSettingsSelect(entries);
  const current = entries.find((config) => config.id === activeSettingsPlatformId) || entries[0];
  activeSettingsPlatformId = current?.id || "";
  platformSettingsList.innerHTML = current ? renderPlatformSettingsCard(current) : "";
}

function renderPlatformSettingsSelect(entries) {
  if (!platformSettingsSelect) return;
  const currentExists = entries.some((config) => config.id === activeSettingsPlatformId);
  if (!currentExists) {
    activeSettingsPlatformId = entries[0]?.id || "";
  }
  platformSettingsSelect.innerHTML = entries
    .map((config) => `<option value="${escapeHtml(config.id)}" ${config.id === activeSettingsPlatformId ? "selected" : ""}>${escapeHtml(config.label)}</option>`)
    .join("");
  platformSettingsSelect.disabled = entries.length <= 1;
}

function renderPlatformSettingsCard(config) {
  const unavailable = !config.available;
  const canRemove = Boolean(config.added && unavailable);
  const keywordValue = escapeHtml((config.keywords || []).join("\n"));
  const discoveryValue = escapeHtml((config.discovery_keywords || []).join("\n"));
  const forumValue = escapeHtml((config.forums || []).join("\n"));
  const cookieValue = escapeHtml(config.cookie || "");

  return `
    <article class="platform-settings-card" data-platform-card="${escapeHtml(config.id)}">
      <div class="platform-settings-head">
        <div>
          <h3>${escapeHtml(config.label)}</h3>
          <p class="platform-settings-note">${escapeHtml(config.description || "")}</p>
        </div>
        <div class="platform-badges">
          <span class="mini-badge ${config.available ? "ok" : "pending"}">${config.available ? "已接入" : "待接入"}</span>
          <span class="mini-badge">${config.selected ? "默认勾选" : "未勾选"}</span>
          ${canRemove ? `<button type="button" class="secondary" data-remove-platform="${escapeHtml(config.id)}">撤销加入</button>` : ""}
        </div>
      </div>
      <div class="config-grid">
        <div class="field">
          <label>默认参与爬取</label>
          <div class="toggle-field">
            <input type="checkbox" data-setting="${escapeHtml(config.id)}" data-field="selected" ${config.selected ? "checked" : ""} ${unavailable ? "disabled" : ""}>
            <span>${unavailable ? "待爬虫接入后可启用" : "启动任务时默认勾选该平台"}</span>
          </div>
        </div>
        <div class="field">
          <label>需要图片</label>
          <div class="toggle-field">
            <input type="checkbox" data-setting="${escapeHtml(config.id)}" data-field="require_images" ${config.require_images ? "checked" : ""}>
            <span>仅保留满足图片要求的内容</span>
          </div>
        </div>
        <div class="field full">
          <label>Cookie</label>
          <textarea data-setting="${escapeHtml(config.id)}" data-field="cookie" placeholder="在这里粘贴该平台的 Cookie">${cookieValue}</textarea>
        </div>
        <div class="field full">
          <label>关键词列表</label>
          <textarea data-setting="${escapeHtml(config.id)}" data-field="keywords" placeholder="每行一个关键词">${keywordValue}</textarea>
          <p class="field-hint">正文筛选关键词，前端保存后会同步到后台运行时配置。</p>
        </div>
        ${config.id === "tieba" ? `
          <div class="field full">
            <label>贴吧列表</label>
            <textarea data-setting="${escapeHtml(config.id)}" data-field="forums" placeholder="每行一个贴吧名">${forumValue}</textarea>
          </div>
        ` : ""}
        ${config.id === "weibo" || config.id === "douyin" ? `
          <div class="field full">
            <label>发现关键词</label>
            <textarea data-setting="${escapeHtml(config.id)}" data-field="discovery_keywords" placeholder="每行一个发现用搜索词，留空则沿用关键词列表">${discoveryValue}</textarea>
          </div>
        ` : ""}
        ${config.id === "weibo" ? `
          <div class="field">
            <label>抓取最近多少天</label>
            <input type="number" min="1" max="3650" data-setting="${escapeHtml(config.id)}" data-field="recent_days" value="${escapeHtml(config.recent_days)}">
          </div>
        ` : ""}
        <div class="field">
          <label>${config.id === "tieba" ? "每个吧最多页数" : "每个关键词最多页数"}</label>
          <input type="number" min="1" max="1000" data-setting="${escapeHtml(config.id)}" data-field="max_pages" value="${escapeHtml(config.max_pages)}">
        </div>
        ${config.id === "xhs" ? `
          <div class="field">
            <label>时间范围</label>
            <select data-setting="${escapeHtml(config.id)}" data-field="note_time">
              <option value="0" ${String(config.note_time) === "0" ? "selected" : ""}>不限</option>
              <option value="1" ${String(config.note_time) === "1" ? "selected" : ""}>一天内</option>
              <option value="2" ${String(config.note_time) === "2" ? "selected" : ""}>一周内</option>
              <option value="3" ${String(config.note_time) === "3" ? "selected" : ""}>半年内</option>
            </select>
          </div>
        ` : ""}
      </div>
    </article>
  `;
}

function collectPlatformSettingsPayload() {
  const payload = {
    added_platforms: (platformSettingsState.known_platforms || [])
      .filter((platform) => platform.added)
      .map((platform) => platform.id),
    platforms: {},
  };

  Object.values(platformSettingsState.platforms || {}).forEach((config) => {
    const id = config.id;
    payload.platforms[id] = {
      selected: readFieldValue(id, "selected", "checkbox", config.selected),
      require_images: readFieldValue(id, "require_images", "checkbox", config.require_images),
      cookie: readFieldValue(id, "cookie", "text", config.cookie || ""),
      keywords: readFieldLines(id, "keywords"),
      discovery_keywords: readFieldLines(id, "discovery_keywords"),
      forums: readFieldLines(id, "forums"),
      recent_days: Number(readFieldValue(id, "recent_days", "number", config.recent_days || 60)),
      max_pages: Number(readFieldValue(id, "max_pages", "number", config.max_pages || 10)),
      note_time: Number(readFieldValue(id, "note_time", "number", config.note_time || 0)),
    };
  });

  return payload;
}

function readFieldValue(platformId, field, type, fallback) {
  const element = document.querySelector(`[data-setting="${platformId}"][data-field="${field}"]`);
  if (!element) return fallback;
  if (type === "checkbox") return Boolean(element.checked);
  return element.value;
}

function readFieldLines(platformId, field) {
  const value = readFieldValue(platformId, field, "text", "");
  return String(value || "")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
}

async function savePlatformSettings() {
  if (!saveSettingsBtn) return;
  saveSettingsBtn.disabled = true;
  saveSettingsBtn.textContent = "保存中...";
  try {
    const payload = collectPlatformSettingsPayload();
    const data = await postJson("/api/platform-settings", payload);
    if (!data.ok) throw new Error("平台设置保存失败");
    platformSettingsState = data;
    settingsDirty = false;
    renderPlatformSelector(data.options || []);
    renderKnownPlatformCatalog(data.known_platforms || []);
    renderPlatformSettingsCards(data.platforms || {});
    await loadStatus();
    settingsStatusText.textContent = "保存成功，后续任务会按新配置运行";
  } catch (error) {
    window.alert(error.message || "平台设置保存失败");
  } finally {
    saveSettingsBtn.disabled = false;
    saveSettingsBtn.textContent = "保存设置";
  }
}

function addKnownPlatform(platformId) {
  settingsDirty = true;
  const target = (platformSettingsState.known_platforms || []).find((platform) => platform.id === platformId);
  const shouldAdd = !target?.added;
  const nextCatalog = (platformSettingsState.known_platforms || []).map((platform) =>
    platform.id === platformId ? { ...platform, added: shouldAdd } : platform,
  );
  platformSettingsState = { ...platformSettingsState, known_platforms: nextCatalog };
  if (shouldAdd && !platformSettingsState.platforms[platformId]) {
    platformSettingsState.platforms[platformId] = {
      id: platformId,
      label: nextCatalog.find((platform) => platform.id === platformId)?.label || platformId,
      description: nextCatalog.find((platform) => platform.id === platformId)?.description || "待接入爬虫",
      available: false,
      added: true,
      selected: false,
      cookie: "",
      keywords: [],
      discovery_keywords: [],
      forums: [],
      recent_days: 60,
      max_pages: 10,
      note_time: 0,
      require_images: true,
    };
  }
  if (!shouldAdd) {
    delete platformSettingsState.platforms[platformId];
    if (activeSettingsPlatformId === platformId) {
      activeSettingsPlatformId = Object.keys(platformSettingsState.platforms || {})[0] || "";
    }
  } else {
    activeSettingsPlatformId = platformId;
  }
  syncPlatformOptionsFromState();
  renderPlatformSelector(platformSettingsState.options || []);
  renderKnownPlatformCatalog(platformSettingsState.known_platforms || []);
  renderPlatformSettingsCards(platformSettingsState.platforms || {});
}

function removeKnownPlatform(platformId) {
  settingsDirty = true;
  const nextCatalog = (platformSettingsState.known_platforms || []).map((platform) =>
    platform.id === platformId ? { ...platform, added: false } : platform,
  );
  delete platformSettingsState.platforms[platformId];
  platformSettingsState = { ...platformSettingsState, known_platforms: nextCatalog };
  if (activeSettingsPlatformId === platformId) {
    activeSettingsPlatformId = Object.keys(platformSettingsState.platforms || {})[0] || "";
  }
  syncPlatformOptionsFromState();
  renderPlatformSelector(platformSettingsState.options || []);
  renderKnownPlatformCatalog(platformSettingsState.known_platforms || []);
  renderPlatformSettingsCards(platformSettingsState.platforms || {});
}

function syncPlatformOptionsFromState() {
  const settingsMap = platformSettingsState.platforms || {};
  platformSettingsState.options = Object.values(settingsMap).map((config) => ({
    id: config.id,
    label: config.label,
    available: config.available,
    added: config.added,
    selected: config.selected,
    description: config.description,
  }));
}

function renderItemList(list, total = cachedItems.length, analyzed = cachedItems.length) {
  const filtered = applyFeedFilter(list || []);
  count.textContent = `共 ${total || 0} 条，已分析 ${analyzed || 0} 条，当前展示 ${filtered.length} 条`;
  items.innerHTML = filtered.length ? filtered.map(renderItem).join("") : emptyCard(filterEmptyMessage());
}

function renderItem(item) {
  const analysis = item.analysis || {};
  const summary = analysis.summary || {};
  const score = Number(summary.total_score);
  const riskLevel = summary.risk_level || statusText(item.analysis_status);
  const reasons = Array.isArray(summary.reasons) ? summary.reasons.slice(0, 5) : [];
  const pics = (item.pics || []).map((pic) => `<img src="${pic.url}" title="${escapeHtml(pic.path)}" loading="lazy">`).join("");
  const matched = Array.isArray(item.matched_keywords) ? item.matched_keywords.join("，") : (item.keyword || "");
  const scoreClass = Number.isFinite(score) ? scoreLevelClass(score) : "pending";
  const platformName = item.platform_name || platformLabel(item.platform);
  const screenName = item.screen_name || "未知用户";
  const avatarText = getAvatarText(screenName);
  const itemId = String(item._id || item.id || "");
  const shouldCollapse = String(item.text || "").length > 140;
  const isExpanded = expandedTextIds.has(itemId);
  const isTracked = cachedWatchItems.some((watchItem) => String(watchItem._id || watchItem.id || "") === itemId);
  const textToggle = shouldCollapse
    ? `<button class="text-toggle" type="button" data-text-toggle="${escapeHtml(itemId)}">${isExpanded ? "收起" : "展开全部"}</button>`
    : "";
  const watchButton = isTracked
    ? `<button class="secondary-action is-joined" type="button" disabled>已加入</button>`
    : `<button class="secondary-action" type="button" data-watch-add="${escapeHtml(itemId)}">加入追踪监测</button>`;

  return `
    <article class="weibo">
      <div class="card-head">
        <div class="user-head">
          <span class="avatar">${escapeHtml(avatarText)}</span>
          <div class="user-copy">
            <strong>${escapeHtml(screenName)}</strong>
          </div>
        </div>
        <div>
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
      <div class="card-actions">${watchButton}</div>
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
      <h3>风险依据</h3>
      <div class="compact-evidence">
        ${(Array.isArray(reasons) ? reasons.slice(0, 4) : []).map((reason) => `<span>${escapeHtml(reason)}</span>`).join("")}
      </div>
      <a class="report-link" href="/report?id=${encodeURIComponent(item._id)}" target="_blank" rel="noopener">查看完整分析报告</a>
    </details>
  `;
}

function emptyCard(message) {
  return `<article class="weibo empty"><p>${escapeHtml(message)}</p></article>`;
}

function renderWatchlist(list, total = cachedWatchItems.length) {
  watchCount.textContent = `共追踪 ${total || 0} 条`;
  watchItems.innerHTML = list.length
    ? list.map(renderWatchItem).join("")
    : emptyCard("当前还没有加入追踪监测的帖子。");
}

function renderSystemStatus() {
  if (selectedPlatformsText) {
    const selected = currentStatus.selected_platforms || [];
    selectedPlatformsText.textContent = selected.length ? selected.map(platformLabel).join(" / ") : "未选择";
  }
  if (engineStatusText) {
    engineStatusText.textContent = currentHealth?.success
      ? (currentHealth.model_ready ? "已加载" : "待初始化")
      : "异常";
  }
  if (statusMeta) {
    statusMeta.textContent = currentHealth?.success
      ? `组件 ${Object.keys(currentHealth.component_status || {}).length} 项`
      : (currentHealth?.error || "状态读取失败");
  }
  if (componentStatusList) {
    const componentStatus = currentHealth?.component_status || {};
    const rows = Object.entries(componentStatus);
    componentStatusList.innerHTML = rows.length
      ? rows.map(([name, status]) => `
          <div class="component-row">
            <span>${escapeHtml(name)}</span>
            <strong>${escapeHtml(String(status))}</strong>
          </div>
        `).join("")
      : `<p class="status-empty">${escapeHtml(currentHealth?.error || "暂无组件状态")}</p>`;
  }
  if (taskSummaryList) {
    const summary = [
      ["运行状态", currentStatus.running ? (currentStatus.paused ? "已暂停" : "运行中") : "空闲"],
      ["平台轮询数", (currentStatus.selected_platforms || []).length || 0],
      ["单平台目标量", currentStatus.platform_item_limit || 0],
      ["累计写入", currentStatus.current_stats?.inserted || 0],
      ["累计重复", currentStatus.current_stats?.skipped || 0],
      ["未命中", currentStatus.current_stats?.unmatched || 0],
      ["丢弃", currentStatus.current_stats?.discarded || 0],
    ];
    taskSummaryList.innerHTML = summary.map(([label, value]) => `
      <div class="component-row">
        <span>${escapeHtml(label)}</span>
        <strong>${escapeHtml(String(value))}</strong>
      </div>
    `).join("");
  }
  if (initErrorsList) {
    const errors = currentHealth?.init_errors || [];
    initErrorsList.innerHTML = errors.length
      ? `<ul class="mini-list">${errors.map((item) => `<li>${escapeHtml(String(item))}</li>`).join("")}</ul>`
      : `<p class="status-empty">当前没有初始化告警。</p>`;
  }
}

function renderWatchItem(item) {
  const analysis = item.analysis || {};
  const summary = analysis.summary || {};
  const score = Number(summary.total_score);
  const riskLevel = summary.risk_level || statusText(item.analysis_status);
  const reasons = Array.isArray(summary.reasons) ? summary.reasons.slice(0, 5) : [];
  const pics = (item.pics || []).map((pic) => `<img src="${pic.url}" title="${escapeHtml(pic.path)}" loading="lazy">`).join("");
  const matched = Array.isArray(item.matched_keywords) ? item.matched_keywords.join("，") : (item.keyword || "");
  const scoreClass = Number.isFinite(score) ? scoreLevelClass(score) : "pending";
  const platformName = item.platform_name || platformLabel(item.platform);
  const screenName = item.screen_name || "未知用户";
  const avatarText = getAvatarText(screenName);
  const itemId = String(item._id || item.id || "");
  const shouldCollapse = String(item.text || "").length > 140;
  const isExpanded = expandedTextIds.has(itemId);
  const textToggle = shouldCollapse
    ? `<button class="text-toggle" type="button" data-text-toggle="${escapeHtml(itemId)}">${isExpanded ? "收起" : "展开全部"}</button>`
    : "";

  return `
    <article class="weibo">
      <div class="card-head">
        <div class="user-head">
          <span class="avatar">${escapeHtml(avatarText)}</span>
          <div class="user-copy">
            <strong>${escapeHtml(screenName)}</strong>
          </div>
        </div>
        <div>
          <div class="meta">
            <span class="platform-chip">${escapeHtml(platformName || "未知平台")}</span>
            <span>${escapeHtml(item.created_at || "")}</span>
            <span>${escapeHtml(item.source || "")}</span>
            <span>命中：${escapeHtml(matched || "无")}</span>
            <span>加入时间：${escapeHtml(item.watch_added_at || "")}</span>
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
      <div class="card-actions">
        <button class="secondary-action danger" type="button" data-watch-remove="${escapeHtml(itemId)}">移出追踪监测</button>
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

async function addToWatchlist(docId) {
  if (!docId) return;
  try {
    const data = await postJson("/api/watchlist", { id: docId });
    if (!data.ok) throw new Error(data.error || "加入追踪监测失败");
    cachedWatchItems = data.items || [];
    renderWatchlist(cachedWatchItems, data.total || 0);
    renderItemList(cachedItems);
  } catch (error) {
    window.alert(error.message || "加入追踪监测失败");
  }
}

async function removeFromWatchlist(docId) {
  if (!docId) return;
  try {
    const res = await fetch(`/api/watchlist/${encodeURIComponent(docId)}`, { method: "DELETE" });
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || "移出追踪监测失败");
    cachedWatchItems = data.items || [];
    renderWatchlist(cachedWatchItems, data.total || 0);
    renderItemList(cachedItems);
  } catch (error) {
    window.alert(error.message || "移出追踪监测失败");
  }
}

function applyFeedFilter(list) {
  return list.filter((item) => matchesFeedFilter(item, currentFeedFilter));
}

function matchesFeedFilter(item, filter) {
  switch (filter) {
    case "weibo":
    case "douyin":
    case "tieba":
    case "xhs":
      return item.platform === filter;
    case "high-risk": {
      const score = Number(item.analysis?.summary?.total_score);
      return Number.isFinite(score) && score >= 40;
    }
    case "analyzed":
      return item.analysis_status === "done" || Boolean(item.analysis?.summary);
    case "recent":
      return isWithinRecentDays(item.created_at, 60);
    case "all":
    default:
      return true;
  }
}

function isWithinRecentDays(value, days) {
  if (!value) return false;
  const normalized = String(value).trim().replace(/\./g, "-").replace(/\//g, "-");
  const time = Date.parse(normalized.replace(" ", "T"));
  if (Number.isNaN(time)) return false;
  const diff = Date.now() - time;
  return diff >= 0 && diff <= days * 24 * 60 * 60 * 1000;
}

function filterEmptyMessage() {
  return {
    all: "暂无数据，点击爬取后会在这里展示多平台内容。",
    weibo: "当前没有符合条件的微博结果。",
    douyin: "当前没有符合条件的抖音结果。",
    tieba: "当前没有符合条件的贴吧结果。",
    xhs: "当前没有符合条件的小红书结果。",
    "high-risk": "当前没有中高风险结果。",
    analyzed: "当前没有已分析完成的结果。",
    recent: "当前没有近两个月内的结果。",
  }[currentFeedFilter] || "当前没有符合筛选条件的结果。";
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

function getAvatarText(name) {
  const text = String(name || "").trim();
  if (!text) return "匿";
  return Array.from(text)[0];
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
