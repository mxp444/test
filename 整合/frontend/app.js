const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));

const state = {
  loggedIn: false,
  role: "user",
  user: "",
  displayName: "",
  phone: "",
  department: "",
  avatarUrl: "",
  avatarPendingFile: null,
  avatarPendingPreview: "",
  items: [],
  watchlist: [],
  watchTotal: 0,
  sources: [],
  status: {},
  logHistory: [],
  activeLogHistoryId: "current",
  health: null,
  platformSettings: { platforms: {}, options: [], known_platforms: [], source_applications: [] },
  selectedPlatforms: [],
  crawlRules: { categories: [] },
  systemSettings: { runtime: {}, engine_options: [], paths: {}, database: {}, platforms: [] },
  accounts: [],
  userManagement: { users: [], role_permissions: {}, departments: {}, roles: {}, activities: [] },
  database: { databases: [], selectedDb: "test", selectedCollection: "", collections: [], documents: [], indexes: [], total: 0, skip: 0, limit: 20, filterText: "{}", sortText: "{ \"_id\": -1 }", editingId: "", activeTab: "documents", showOptions: false, viewMode: "list" },
  databaseRootCollapsed: false,
  collapsedDatabases: {},
  expandedCrawlRules: {},
  feedFilter: "all",
  activeView: "home",
  settingsDirty: false,
  systemSettingsDirty: false,
  activeSettingsPlatformId: "",
  monitorLimit: localStorage.getItem("monitorLimit") || "20",
  riskAnalysisFilter: "medium-high",
  expandedAccount: "",
  collapsedNavGroups: { front: false, admin: false },
  accountMenuOpen: false,
};

const views = ["home", "collection", "monitor", "tracking", "risk", "profile", "admin-platforms", "admin-tasks", "admin-models", "admin-logs", "admin-database", "admin-users", "admin-user-management", "admin-settings"];
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
  $("#accountMenuBtn")?.addEventListener("click", (event) => {
    event.stopPropagation();
    toggleAccountMenu();
  });
  $("#accountProfileLink")?.addEventListener("click", (event) => {
    event.preventDefault();
    toggleAccountMenu(false);
    switchView("profile");
  });
  document.addEventListener("click", (event) => {
    const root = $("#accountMenu");
    if (!root || root.contains(event.target)) return;
    toggleAccountMenu(false);
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") toggleAccountMenu(false);
  });
  updateLoginButtonState();

  $$(".nav-link[data-view]").forEach((link) => {
    link.addEventListener("click", (event) => {
      event.preventDefault();
      switchView(link.dataset.view);
    });
  });
  $$("[data-nav-toggle]").forEach((button) => {
    button.addEventListener("click", () => toggleNavGroup(button.dataset.navToggle));
  });

  $("#refreshBtn")?.addEventListener("click", refreshAll);
  $("#toggleBtn")?.addEventListener("click", toggleCrawl);
  $("#analyzeOldBtn")?.addEventListener("click", analyzeOldItems);
  $("#clearLogsBtn")?.addEventListener("click", clearCurrentLogs);
  $("#runDiagnosticsBtn")?.addEventListener("click", runCrawlerDiagnostics);
  $("#platformSelector")?.addEventListener("change", (event) => {
    if (event.target.matches("input[name='platform']")) {
      state.selectedPlatforms = $$("input[name='platform']:checked").map((input) => input.value);
    }
  });
  $("#logHistorySelect")?.addEventListener("change", (event) => {
    state.activeLogHistoryId = event.target.value || "current";
    renderLogPanel();
  });
  $("#saveSettingsBtn")?.addEventListener("click", () => savePlatformSettings());
  $("#systemSettings")?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-system-save]");
    if (button) saveSystemSettings(button.dataset.systemSave);
  });
  $("#systemSettings")?.addEventListener("input", () => {
    state.systemSettingsDirty = true;
  });
  $("#systemSettings")?.addEventListener("change", () => {
    state.systemSettingsDirty = true;
  });
  $("#resetEngineBtn")?.addEventListener("click", resetAnalysisEngine);
  $("#sourceForm")?.addEventListener("submit", saveCollectionSource);
  $("#resetSourceBtn")?.addEventListener("click", resetSourceForm);
  $("#profileForm")?.addEventListener("submit", saveProfile);
  $("#profileAvatarChooseBtn")?.addEventListener("click", () => $("#profileAvatarInput")?.click());
  $("#profileAvatarInput")?.addEventListener("change", handleAvatarSelection);
  $("#profileAvatarSaveBtn")?.addEventListener("click", saveAvatar);
  $("#profileAvatarDeleteBtn")?.addEventListener("click", deleteAvatar);
  $("#passwordForm")?.addEventListener("submit", savePassword);
  $("#searchForm")?.addEventListener("submit", (event) => {
    event.preventDefault();
    renderMonitor();
  });
  $("#resetSearchBtn")?.addEventListener("click", resetSearchRules);
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
  $("#sourceTable")?.addEventListener("change", (event) => {
    const status = event.target.closest("[data-source-status]");
    if (status) updateCollectionSourceStatus(status.dataset.sourceStatus, status.value);
  });

  $("#monitorFilters")?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-filter]");
    if (!button) return;
    state.feedFilter = button.dataset.filter;
    $$("#monitorFilters .channel-pill").forEach((pill) => pill.classList.toggle("is-active", pill === button));
    renderMonitor();
  });

  document.addEventListener("click", (event) => {
    const watchButton = event.target.closest("[data-watch-toggle]");
    if (watchButton) toggleWatchItem(watchButton.dataset.watchToggle);
  });

  $("#riskLevelFilters")?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-risk-filter]");
    if (!button) return;
    state.riskAnalysisFilter = button.dataset.riskFilter;
    renderRiskAnalysis();
  });

  $("#knownPlatformCatalog")?.addEventListener("click", (event) => {
    const addButton = event.target.closest("[data-add-platform]");
    if (addButton) addKnownPlatform(addButton.dataset.addPlatform);
  });

  $("#sourceApplicationsPanel")?.addEventListener("click", (event) => {
    const approveButton = event.target.closest("[data-approve-source]");
    const rejectButton = event.target.closest("[data-reject-source]");
    if (approveButton) reviewPlatformApplication(approveButton.dataset.approveSource, "approve");
    if (rejectButton) reviewPlatformApplication(rejectButton.dataset.rejectSource, "reject");
  });

  $("#platformSettingsList")?.addEventListener("input", (event) => {
    updatePlatformSettingDraft(event.target);
    state.settingsDirty = true;
    updateSettingsSaveState();
  });

  $("#platformSettingsList")?.addEventListener("change", (event) => {
    updatePlatformSettingDraft(event.target);
    state.settingsDirty = true;
    updateSettingsSaveState();
  });

  $("#platformSettingsList")?.addEventListener("click", (event) => {
    const removeButton = event.target.closest("[data-remove-platform]");
    if (removeButton) removeKnownPlatform(removeButton.dataset.removePlatform);
  });

  $("#platformSettingsSelect")?.addEventListener("change", (event) => {
    readActivePlatformSettingsIntoState();
    state.activeSettingsPlatformId = event.target.value;
    renderPlatformSettingsCards();
  });

  $("#ruleCards")?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-rule-toggle]");
    if (!button) return;
    const index = button.dataset.ruleToggle;
    state.expandedCrawlRules[index] = !state.expandedCrawlRules[index];
    renderCrawlRules();
  });

  $("#accountTable")?.addEventListener("click", (event) => {
    const edit = event.target.closest("[data-account-edit]");
    const cancel = event.target.closest("[data-account-cancel]");
    const save = event.target.closest("[data-account-save]");
    const toggle = event.target.closest("[data-account-toggle]");
    const reset = event.target.closest("[data-account-reset]");
    if (edit) toggleAccountDetails(edit.dataset.accountEdit);
    if (cancel) closeAccountDetails(cancel.dataset.accountCancel);
    if (save) saveInlineAccount(save.dataset.accountSave);
    if (toggle) toggleAccount(toggle.dataset.accountToggle);
    if (reset) resetAccountPassword(reset.dataset.accountReset);
  });

  $("#dbRefreshBtn")?.addEventListener("click", refreshDatabaseWorkbench);
  $("#dbTreeSearch")?.addEventListener("input", renderDatabaseTree);
  $("#databaseTree")?.addEventListener("click", (event) => {
    const rootAdd = event.target.closest("[data-db-root-add]");
    const rootToggle = event.target.closest("[data-db-root-toggle]");
    const dbToggle = event.target.closest("[data-db-toggle]");
    const dbCreateCollection = event.target.closest("[data-db-create-collection]");
    const dbDrop = event.target.closest("[data-db-drop]");
    const collectionDrop = event.target.closest("[data-db-drop-collection]");
    const dbButton = event.target.closest("[data-db-name]");
    const collectionButton = event.target.closest("[data-db-collection]");
    if (rootAdd) {
      createDatabaseFromRoot();
    } else if (rootToggle) {
      state.databaseRootCollapsed = !state.databaseRootCollapsed;
      renderDatabaseTree();
    } else if (dbCreateCollection) {
      createDatabaseCollection(dbCreateCollection.dataset.dbCreateCollection);
    } else if (dbDrop) {
      dropDatabase(dbDrop.dataset.dbDrop);
    } else if (collectionDrop) {
      dropDatabaseCollection(collectionDrop.dataset.dbName, collectionDrop.dataset.dbDropCollection);
    } else if (collectionButton) {
      selectDatabaseCollection(collectionButton.dataset.dbName, collectionButton.dataset.dbCollection);
    } else if (dbToggle) {
      toggleDatabaseCollapsed(dbToggle.dataset.dbToggle);
    } else if (dbButton) {
      selectDatabase(dbButton.dataset.dbName);
    }
  });
  $("#databaseCollectionsPanel")?.addEventListener("click", (event) => {
    const collection = event.target.closest("[data-open-collection]");
    if (collection) selectDatabaseCollection(collection.dataset.openDb, collection.dataset.openCollection);
  });
  $("#databaseDocumentsPanel")?.addEventListener("click", (event) => {
    const edit = event.target.closest("[data-db-edit]");
    const del = event.target.closest("[data-db-delete]");
    const prev = event.target.closest("[data-db-prev]");
    const next = event.target.closest("[data-db-next]");
    const query = event.target.closest("[data-db-query]");
    const add = event.target.closest("[data-db-add-document]");
    const reset = event.target.closest("[data-db-reset]");
    const clear = event.target.closest("[data-db-clear-documents]");
    if (edit) editDatabaseDocument(edit.dataset.dbEdit);
    if (del) deleteDatabaseDocument(del.dataset.dbDelete);
    if (prev) pageDatabaseDocuments(-1);
    if (next) pageDatabaseDocuments(1);
    if (query) queryDatabaseDocuments();
    if (add) newDatabaseDocument();
    if (reset) resetDatabaseQuery();
    if (clear) clearDatabaseDocuments();
  });
  $("#databaseDocumentsPanel")?.addEventListener("input", (event) => {
    if (event.target.id === "dbFilterInput") state.database.filterText = event.target.value;
    if (event.target.id === "dbFilterInput") renderDatabaseQueryButtons();
  });
  $("#databaseDocumentsPanel")?.addEventListener("change", (event) => {
    if (event.target.id === "dbLimitSelect") changeDatabaseLimit(event.target.value);
  });
  $("#dbModalCloseBtn")?.addEventListener("click", closeDatabaseModal);
  $("#dbSaveDocumentBtn")?.addEventListener("click", saveDatabaseDocument);
  $("#dbClearEditorBtn")?.addEventListener("click", clearDatabaseEditor);
  $("#dbModal")?.addEventListener("click", (event) => {
    if (event.target.id === "dbModal") closeDatabaseModal();
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
  await Promise.allSettled([loadHealth(), loadStatus(), loadLogHistory(), loadItems(), loadWatchlist(), loadCollectionSources(), loadPlatformSettings(), loadCrawlRules(), loadSystemSettings(), loadAccounts(), loadUserManagement()]);
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

async function loadLogHistory() {
  if (state.role !== "admin") return;
  try {
    const data = await fetchJson("/api/crawl/log-history");
    state.logHistory = data.items || [];
  } catch {
    state.logHistory = [];
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

async function loadWatchlist() {
  try {
    const data = await fetchJson("/api/watchlist?limit=300");
    state.watchlist = data.items || [];
    state.watchTotal = data.total || state.watchlist.length;
  } catch {
    state.watchlist = [];
    state.watchTotal = 0;
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
    state.platformSettings = { platforms: {}, options: [], known_platforms: [], source_applications: [] };
  }
}

async function loadCrawlRules() {
  if (state.role !== "admin") return;
  try {
    state.crawlRules = await fetchJson("/api/admin/crawl-rules");
  } catch {
    state.crawlRules = { categories: [] };
  }
}

async function loadSystemSettings() {
  if (state.role !== "admin" || state.systemSettingsDirty) return;
  try {
    state.systemSettings = await fetchJson("/api/admin/system-settings");
  } catch {
    state.systemSettings = { runtime: {}, engine_options: [], paths: {}, database: {}, platforms: [] };
  }
}

async function loadAccounts() {
  if (state.role !== "admin") return;
  try {
    const data = await fetchJson("/api/admin/accounts");
    state.accounts = data.items || [];
  } catch {
    state.accounts = [];
  }
}

async function loadUserManagement() {
  if (state.role !== "admin") return;
  try {
    state.userManagement = await fetchJson("/api/admin/user-management");
  } catch {
    state.userManagement = { users: [], role_permissions: {}, departments: {}, roles: {}, activities: [] };
  }
}

async function loadDatabaseOverview() {
  if (state.role !== "admin") return;
  try {
    const data = await fetchJson("/api/admin/database/overview");
    state.database.databases = data.databases || [];
    if (!state.database.selectedDb && state.database.databases.length) {
      state.database.selectedDb = state.database.databases[0].name;
    }
    const current = state.database.databases.find((db) => db.name === state.database.selectedDb);
    state.database.collections = current?.collections || [];
  } catch {
    state.database.databases = [];
    state.database.collections = [];
  }
}

async function loadDatabaseCollections(dbName = state.database.selectedDb) {
  if (state.role !== "admin" || !dbName) return;
  try {
    const data = await fetchJson(`/api/admin/database/collections?db=${encodeURIComponent(dbName)}`);
    state.database.selectedDb = data.db;
    state.database.collections = data.collections || [];
  } catch (error) {
    window.alert(error.message);
  }
}

async function loadDatabaseDocuments() {
  if (state.role !== "admin" || !state.database.selectedDb || !state.database.selectedCollection) return;
  const params = new URLSearchParams({
    db: state.database.selectedDb,
    collection: state.database.selectedCollection,
    filter: state.database.filterText || "{}",
    sort: state.database.sortText || "{}",
    limit: String(state.database.limit || 20),
    skip: String(state.database.skip || 0),
  });
  try {
    const data = await fetchJson(`/api/admin/database/documents?${params}`);
    state.database.documents = data.documents || [];
    state.database.total = data.total || 0;
    state.database.skip = data.skip || 0;
    state.database.limit = data.limit || state.database.limit || 20;
  } catch (error) {
    window.alert(error.message);
  }
}

async function loadDatabaseIndexes() {
  if (state.role !== "admin" || !state.database.selectedDb || !state.database.selectedCollection) return;
  const params = new URLSearchParams({ db: state.database.selectedDb, collection: state.database.selectedCollection });
  try {
    const data = await fetchJson(`/api/admin/database/indexes?${params}`);
    state.database.indexes = data.indexes || [];
  } catch {
    state.database.indexes = [];
  }
}

function renderAll() {
  renderHealth();
  renderTaskControl();
  renderHome();
  renderCollectionSources();
  renderMonitorFilters();
  renderMonitor();
  renderTracking();
  renderRiskAnalysis();
  renderProfile();
  renderAdminStatus();
  renderAdminSettings();
  renderCrawlRules();
  renderSystemSettings();
  renderAccounts();
  renderUserManagement();
}

function applyRole() {
  document.body.dataset.role = state.role;
  document.body.classList.toggle("is-authenticated", state.loggedIn);
  $$(".admin-only").forEach((el) => el.classList.toggle("is-hidden", state.role !== "admin"));
  updateNavGroupState();
  renderHeaderAccount();
  renderProfile();
}

function renderHeaderAccount() {
  const name = state.loggedIn ? (state.displayName || state.user || "未登录") : "未登录";
  const roleText = state.loggedIn ? (state.role === "admin" ? "Admin" : "User") : "Guest";
  const emailText = state.loggedIn ? (state.user || "未设置邮箱") : "未登录";
  const avatar = getAvatarText(name);
  const imageUrl = currentAvatarUrl();
  const avatarEl = $("#accountMenuAvatar");
  if (avatarEl) {
    avatarEl.innerHTML = "";
    avatarEl.classList.toggle("has-image", Boolean(imageUrl));
    if (imageUrl) {
      const img = document.createElement("img");
      img.src = imageUrl;
      img.alt = "用户头像";
      avatarEl.appendChild(img);
    } else {
      avatarEl.textContent = avatar;
    }
  }
  $("#accountMenuName").textContent = name;
  $("#accountMenuRole").textContent = roleText;
  $("#accountMenuPanelName").textContent = name;
  $("#accountMenuPanelEmail").textContent = emailText;
  toggleAccountMenu(false);
}

function toggleAccountMenu(forceOpen) {
  const shouldOpen = typeof forceOpen === "boolean" ? forceOpen : !state.accountMenuOpen;
  state.accountMenuOpen = shouldOpen;
  $("#accountMenuBtn")?.setAttribute("aria-expanded", String(shouldOpen));
  $("#accountMenuPanel")?.classList.toggle("is-hidden", !shouldOpen);
}

function toggleNavGroup(group) {
  if (!group || !(group in state.collapsedNavGroups)) return;
  state.collapsedNavGroups[group] = !state.collapsedNavGroups[group];
  updateNavGroupState();
}

function updateNavGroupState() {
  $$("[data-nav-group]").forEach((groupEl) => {
    const group = groupEl.dataset.navGroup;
    const collapsed = Boolean(state.collapsedNavGroups[group]);
    groupEl.classList.toggle("is-collapsed", collapsed);
    groupEl.querySelector("[data-nav-toggle]")?.setAttribute("aria-expanded", String(!collapsed));
  });
}

function switchView(view) {
  if (!state.loggedIn) {
    state.activeView = defaultViewForRole();
    return;
  }
  if (view === "summary") view = "home";
  if (view === "search") view = "monitor";
  if (view === "warning") view = "risk";
  const target = views.includes(view) ? view : "home";
  if (adminViews.has(target) && state.role !== "admin") {
    window.alert("普通用户不能访问后台管理功能。");
    return switchView("home");
  }
  state.activeView = target;
  views.forEach((name) => $(`#${name}View`)?.classList.toggle("is-active", name === target));
  $$(".nav-link[data-view]").forEach((link) => link.classList.toggle("is-active", link.dataset.view === target));
  location.hash = target === "home" ? "summary" : target;
  if (target === "admin-database") refreshDatabaseWorkbench();
}

function restoreSession() {
  try {
    const session = JSON.parse(localStorage.getItem("monitorSession") || "null");
    if (!session?.username || !session?.role) return;
    state.loggedIn = true;
    state.user = session.username;
    state.role = session.role === "admin" ? "admin" : "user";
    state.displayName = session.display_name || session.displayName || session.username;
    state.phone = session.phone || "";
    state.department = session.department || "";
    state.avatarUrl = session.avatar_url || "";
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
  state.phone = user.phone || "";
  state.department = user.department || "";
  state.avatarUrl = user.avatar_url || "";
  state.avatarPendingFile = null;
  state.avatarPendingPreview = "";
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
  state.phone = "";
  state.department = "";
  state.avatarUrl = "";
  state.avatarPendingFile = null;
  state.avatarPendingPreview = "";
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
  const activeCrawling = Boolean(status.running && !status.paused);
  const diagnosticsButton = $("#runDiagnosticsBtn");
  if (diagnosticsButton) diagnosticsButton.disabled = activeCrawling;
  $("#runState").textContent = status.running ? (status.paused ? "已暂停" : "采集中") : "空闲";
  $("#runState").className = status.running ? (status.paused ? "badge paused" : "badge") : "badge idle";
  $("#toggleBtn").textContent = status.running && !status.paused ? "暂停" : "启动采集";
  const stats = status.current_stats || status.last_result || {};
  $("#lastResult").textContent = `写入 ${stats.inserted || 0}，重复 ${stats.skipped || 0}，未命中 ${stats.unmatched || 0}，丢弃 ${stats.discarded || 0}`;
  $("#lastError").textContent = status.last_error ? `错误：${status.last_error}` : "";
  renderLogPanel();
  const runningSelected = new Set(status.selected_platforms || []);
  const draftSelected = new Set(state.selectedPlatforms || []);
  const useRunningSelection = Boolean(activeCrawling && runningSelected.size);
  const useDraftSelection = Boolean(!useRunningSelection && draftSelected.size);
  $("#platformSelector").innerHTML = (state.platformSettings.options || []).map((option) => `
    <label class="${option.available ? "" : "is-pending"}">
      <input type="checkbox" name="platform" value="${escapeHtml(option.id)}" ${(useRunningSelection ? runningSelected.has(option.id) : (useDraftSelection ? draftSelected.has(option.id) : option.selected)) ? "checked" : ""} ${option.available && !activeCrawling ? "" : "disabled"}>
      ${escapeHtml(option.label)}
    </label>
  `).join("");
  if (useRunningSelection) {
    state.selectedPlatforms = Array.from(runningSelected);
  } else if (!useDraftSelection) {
    state.selectedPlatforms = (state.platformSettings.options || []).filter((option) => option.available && option.selected).map((option) => option.id);
  }
}

function renderLogPanel() {
  const select = $("#logHistorySelect");
  const panel = $("#logsPanel");
  const meta = $("#logsMeta");
  if (!select || !panel || !meta) return;
  const currentValue = state.activeLogHistoryId || "current";
  select.innerHTML = `<option value="current">当前控制台</option>${(state.logHistory || []).map((item) => {
    const label = `${item.saved_at || ""} · ${item.event_label || "历史日志"} · ${(item.logs || []).length} 条`;
    return `<option value="${escapeHtml(item.id)}">${escapeHtml(label)}</option>`;
  }).join("")}`;
  select.value = (currentValue === "current" || (state.logHistory || []).some((item) => item.id === currentValue)) ? currentValue : "current";
  state.activeLogHistoryId = select.value;
  if (state.activeLogHistoryId !== "current") {
    const item = (state.logHistory || []).find((entry) => entry.id === state.activeLogHistoryId);
    const logs = item?.logs || [];
    panel.textContent = logs.length ? logs.join("\n") : "该历史记录暂无日志内容。";
    meta.textContent = item ? `${item.event_label || "历史日志"}，保存于 ${item.saved_at || "--"}` : "历史记录不存在";
    return;
  }
  const status = state.status || {};
  const logs = status.logs || [];
  panel.textContent = logs.length ? logs.join("\n") : "等待爬取任务启动...";
  meta.textContent = status.running ? `当前 ${logs.length} 条日志` : (logs.length ? `当前 ${logs.length} 条日志` : "当前没有运行任务");
}

async function toggleCrawl() {
  try {
    const selected = $$("input[name='platform']:checked").map((input) => input.value);
    state.selectedPlatforms = selected;
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

async function clearCurrentLogs() {
  try {
    const data = await fetchJson("/api/crawl/logs/clear", { method: "POST", body: "{}" });
    state.status = data.status || state.status || {};
    state.activeLogHistoryId = "current";
    await loadLogHistory();
    renderLogPanel();
  } catch (error) {
    window.alert(error.message);
  }
}

async function runCrawlerDiagnostics() {
  try {
    const data = await fetchJson("/api/crawl/diagnostics", { method: "POST", body: "{}" });
    state.status = data.status || state.status || {};
    state.activeLogHistoryId = "current";
    renderLogPanel();
    setTimeout(loadStatusAndRenderLogs, 900);
  } catch (error) {
    window.alert(error.message);
  }
}

async function loadStatusAndRenderLogs() {
  await loadStatus();
  renderLogPanel();
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
  $("#dailyTrendChart").innerHTML = renderLineChart(dailyTrend(state.items, 14));
  $("#dailyTrendMeta").textContent = `最近14天，累计 ${state.items.length} 条`;
  $("#riskDistribution").innerHTML = renderDonutChart(countBy(state.items, riskBucket));
  $("#platformDistribution").innerHTML = renderDonutChart(countBy(state.items, (item) => platformLabel(item.platform)));
  $("#homeMeta").textContent = `展示 ${Math.min(6, highRisk.length)} 条`;
  $("#homeHighRiskItems").innerHTML = renderCompactRows(highRisk.slice(0, 6));
}

function renderMonitorFilters() {
  const filters = [
    ["all", "全部"], ["weibo", "微博"], ["douyin", "抖音"], ["tieba", "贴吧"], ["xhs", "小红书"], ["high", "高风险"], ["recent", "近两个月"],
  ];
  $("#monitorFilters").innerHTML = filters.map(([id, label]) => `<button class="channel-pill ${state.feedFilter === id ? "is-active" : ""}" type="button" data-filter="${id}">${label}</button>`).join("");
}

function renderRiskLevelFilters() {
  const filters = [["all", "全部"], ["medium", "中风险"], ["medium-high", "中高风险"], ["high", "高风险"]];
  $("#riskLevelFilters").innerHTML = filters.map(([id, label]) => `<button class="channel-pill ${state.riskAnalysisFilter === id ? "is-active" : ""}" type="button" data-risk-filter="${id}">${label}</button>`).join("");
}

function renderMonitor() {
  const list = filteredItems();
  const visible = limitedMonitorItems(list);
  if ($("#monitorLimitSelect")) $("#monitorLimitSelect").value = state.monitorLimit;
  $("#count").textContent = `共 ${state.total || 0} 条，筛选 ${list.length} 条，当前展示 ${visible.length} 条`;
  $("#items").innerHTML = visible.length ? visible.map(renderItem).join("") : emptyCard("当前没有符合条件的舆情数据。");
}

function renderTracking() {
  $("#trackingMeta").textContent = `已追踪 ${state.watchTotal || state.watchlist.length} 条`;
  $("#trackingItems").innerHTML = state.watchlist.length
    ? state.watchlist.map((item) => renderItem(item, { trackingView: true })).join("")
    : emptyCard("还没有加入追踪的舆情。");
}

function resetSearchRules() {
  $("#searchForm")?.reset();
  renderMonitor();
}

function renderRiskAnalysis() {
  const riskItems = state.items.filter((item) => ["中高风险", "高风险"].includes(riskBucket(item)));
  $("#riskTrendChart").innerHTML = renderLineChart(dailyTrend(riskItems, 14));
  $("#riskTrendMeta").textContent = `最近14天，中高风险 ${riskItems.length} 条`;
  $("#riskTypeChart").innerHTML = renderDonutChart(countBy(state.items, inferRiskType));
  $("#sentimentChart").innerHTML = renderDonutChart(countBy(state.items, inferSentiment));
  renderRiskLevelFilters();
  const list = riskAnalysisItems();
  const label = riskFilterLabel(state.riskAnalysisFilter);
  $("#riskMeta").textContent = `按总舆情 ${state.total || state.items.length || 0} 条分析，${label} ${list.length} 条`;
  $("#riskItems").innerHTML = list.length ? list.slice(0, 20).map(renderItem).join("") : emptyCard(`当前暂无${label}分析结果。`);
}

function renderProfile() {
  if (!$("#profileUsername")) return;
  $("#profileUsername").value = state.user || "";
  $("#profileDisplayName").value = state.displayName || "";
  $("#profilePhone").value = state.phone || "";
  $("#profileDepartment").value = state.department || "";
  const name = state.displayName || state.user || "未登录";
  const avatar = getAvatarText(name);
  $("#profileHeroName").textContent = name;
  $("#profileHeroAccount").textContent = state.user || "未登录";
  $("#profileEmailBind").textContent = "当前未绑定邮箱";
  renderProfileAvatar($("#profileAvatarLarge"), avatar, currentAvatarUrl());
  renderProfileAvatar($("#profileAvatarMedium"), avatar, currentAvatarUrl());
  $("#profileAvatarSaveBtn").disabled = !state.avatarPendingFile;
  $("#profileAvatarHint").textContent = state.avatarPendingFile
    ? `已选择 ${state.avatarPendingFile.name}，点击保存后生效。`
    : (state.avatarUrl ? "当前使用上传头像，可重新上传或删除。" : "当前使用用户名首字作为头像，可上传图片作为个人头像。");
  $("#profileRoleMeta").textContent = state.role === "admin" ? "管理员" : "用户";
  $("#profileWatchCount").textContent = state.watchTotal || state.watchlist.length || 0;
  $("#profilePlatformCount").textContent = new Set(state.items.map((item) => item.platform).filter(Boolean)).size || 0;
  $("#profileRegisterTime").textContent = "2026年5月";
}

async function saveProfile(event) {
  event.preventDefault();
  const message = $("#profileMessage");
  message.textContent = "";
  try {
    const data = await fetchJson("/api/account/profile", {
      method: "PUT",
      body: JSON.stringify({
        display_name: $("#profileDisplayName").value,
        phone: $("#profilePhone").value,
        department: $("#profileDepartment").value,
      }),
    });
    updateSessionUser(data.user);
    applyRole();
    message.textContent = "个人资料已保存。";
    message.className = "form-message ok";
  } catch (error) {
    message.textContent = error.message;
    message.className = "form-message error";
  }
}

function handleAvatarSelection(event) {
  const file = event.target.files?.[0];
  if (!file) return;
  if (!file.type.startsWith("image/")) {
    window.alert("请选择图片文件。");
    event.target.value = "";
    return;
  }
  if (state.avatarPendingPreview) URL.revokeObjectURL(state.avatarPendingPreview);
  state.avatarPendingFile = file;
  state.avatarPendingPreview = URL.createObjectURL(file);
  renderProfile();
}

async function saveAvatar() {
  if (!state.avatarPendingFile) return;
  const message = $("#profileMessage");
  message.textContent = "";
  const form = new FormData();
  form.append("avatar", state.avatarPendingFile);
  try {
    const res = await fetch("/api/account/avatar", {
      method: "POST",
      headers: { "X-User-Role": state.role, "X-User-Name": state.user },
      body: form,
    });
    const data = await res.json();
    if (!res.ok || data.ok === false) throw new Error(data.error || "头像保存失败");
    if (state.avatarPendingPreview) URL.revokeObjectURL(state.avatarPendingPreview);
    state.avatarPendingFile = null;
    state.avatarPendingPreview = "";
    $("#profileAvatarInput").value = "";
    updateSessionUser(data.user);
    applyRole();
    message.textContent = "头像已保存。";
    message.className = "form-message ok";
  } catch (error) {
    message.textContent = error.message;
    message.className = "form-message error";
  }
}

async function deleteAvatar() {
  if (!state.avatarUrl && !state.avatarPendingFile) return;
  if (state.avatarPendingFile && !state.avatarUrl) {
    if (state.avatarPendingPreview) URL.revokeObjectURL(state.avatarPendingPreview);
    state.avatarPendingFile = null;
    state.avatarPendingPreview = "";
    $("#profileAvatarInput").value = "";
    renderProfile();
    return;
  }
  try {
    const data = await fetchJson("/api/account/avatar", { method: "DELETE", body: "{}" });
    if (state.avatarPendingPreview) URL.revokeObjectURL(state.avatarPendingPreview);
    state.avatarPendingFile = null;
    state.avatarPendingPreview = "";
    $("#profileAvatarInput").value = "";
    updateSessionUser(data.user);
    applyRole();
  } catch (error) {
    window.alert(error.message);
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

function renderAccounts() {
  if (state.role !== "admin" || !$("#accountTable")) return;
  $("#accountMeta").textContent = `共 ${state.accounts.length} 个账号`;
  $("#accountTable").innerHTML = state.accounts.length ? `
    <table><thead><tr><th>用户名</th><th>显示名称</th><th>角色</th><th>状态</th><th>部门</th><th>联系电话</th><th>操作</th></tr></thead><tbody>
      ${state.accounts.map((account) => `<tr>
        <td>${escapeHtml(account.username)}</td>
        <td>${escapeHtml(account.display_name || "")}</td>
        <td>${account.role === "admin" ? "管理员" : "普通用户"}</td>
        <td><span class="mini-badge ${account.enabled ? "ok" : "pending"}">${account.enabled ? "启用" : "禁用"}</span></td>
        <td>${escapeHtml(account.department || "")}</td>
        <td>${escapeHtml(account.phone || "")}</td>
        <td>
          <button type="button" data-account-edit="${escapeHtml(account.username)}">编辑</button>
          <button type="button" data-account-toggle="${escapeHtml(account.username)}">${account.enabled ? "禁用" : "启用"}</button>
          <button type="button" class="danger-inline" data-account-reset="${escapeHtml(account.username)}">重置密码</button>
        </td>
      </tr>${state.expandedAccount === account.username ? renderAccountDetailRow(account) : ""}`).join("")}
    </tbody></table>` : emptyTable("暂无账号。");
}

function renderAccountDetailRow(account) {
  return `<tr class="account-detail-row"><td colspan="7">
    <div class="inline-account-editor">
      <label>用户名<input data-account-field="username" value="${escapeHtml(account.username)}"></label>
      <label>显示名称<input data-account-field="display_name" value="${escapeHtml(account.display_name || "")}"></label>
      <label>联系电话<input data-account-field="phone" value="${escapeHtml(account.phone || "")}"></label>
      <label>所属部门<input data-account-field="department" value="${escapeHtml(account.department || "")}"></label>
      <label>账号角色<select data-account-field="role"><option value="user" ${account.role === "admin" ? "" : "selected"}>普通用户</option><option value="admin" ${account.role === "admin" ? "selected" : ""}>管理员</option></select></label>
      <label>账号状态<select data-account-field="enabled"><option value="true" ${account.enabled ? "selected" : ""}>启用</option><option value="false" ${account.enabled ? "" : "selected"}>禁用</option></select></label>
      <div class="form-actions full">
        <button class="primary" type="button" data-account-save="${escapeHtml(account.username)}">保存修改</button>
        <button type="button" data-account-cancel="${escapeHtml(account.username)}">收起</button>
      </div>
    </div>
  </td></tr>`;
}

function toggleAccountDetails(username) {
  state.expandedAccount = state.expandedAccount === username ? "" : username;
  renderAccounts();
}

function closeAccountDetails(username) {
  if (state.expandedAccount === username) state.expandedAccount = "";
  renderAccounts();
}

async function saveInlineAccount(original) {
  const row = document.querySelector(`[data-account-save="${CSS.escape(original)}"]`)?.closest(".account-detail-row");
  if (!row) return;
  const payload = {
    username: row.querySelector('[data-account-field="username"]').value,
    display_name: row.querySelector('[data-account-field="display_name"]').value,
    phone: row.querySelector('[data-account-field="phone"]').value,
    department: row.querySelector('[data-account-field="department"]').value,
    role: row.querySelector('[data-account-field="role"]').value,
    enabled: row.querySelector('[data-account-field="enabled"]').value === "true",
  };
  try {
    const data = await fetchJson(`/api/admin/accounts/${encodeURIComponent(original)}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    });
    state.accounts = data.items || [];
    state.expandedAccount = payload.username;
    renderAccounts();
  } catch (error) {
    window.alert(error.message);
  }
}

async function toggleAccount(username) {
  const account = state.accounts.find((item) => item.username === username);
  if (!account) return;
  try {
    const data = await fetchJson(`/api/admin/accounts/${encodeURIComponent(username)}`, {
      method: "PUT",
      body: JSON.stringify({ ...account, enabled: !account.enabled }),
    });
    state.accounts = data.items || [];
    renderAccounts();
  } catch (error) {
    window.alert(error.message);
  }
}

async function resetAccountPassword(username) {
  const password = window.prompt(`请输入 ${username} 的新密码（至少 6 位）`);
  if (!password) return;
  try {
    await fetchJson(`/api/admin/accounts/${encodeURIComponent(username)}/reset-password`, {
      method: "POST",
      body: JSON.stringify({ password }),
    });
    window.alert("密码已重置。");
  } catch (error) {
    window.alert(error.message);
  }
}

function renderUserManagement() {
  if (state.role !== "admin" || !$("#rolePermissionCards")) return;
  const data = state.userManagement || {};
  const presets = data.role_permissions || {};
  $("#rolePermissionCards").innerHTML = Object.entries(presets).map(([role, config]) => `
    <article class="admin-card">
      <h3>${escapeHtml(config.label || role)}</h3>
      <p>${escapeHtml(config.scope || "")}</p>
      <div class="chip-list">${(config.permissions || []).map((item) => `<span>${escapeHtml(item)}</span>`).join("")}</div>
      ${(config.denied || []).length ? `<p class="field-hint">禁止：${escapeHtml((config.denied || []).join("、"))}</p>` : ""}
    </article>
  `).join("") || emptyCard("暂无角色权限配置。");

  const users = data.users || [];
  $("#userGroupMeta").textContent = `共 ${users.length} 个用户`;
  $("#userGroupChart").innerHTML = renderBars(data.departments || {}, users.length || 1);
  $("#userScopeTable").innerHTML = users.length ? `
    <table><thead><tr><th>用户</th><th>角色</th><th>部门</th><th>状态</th><th>操作范围</th></tr></thead><tbody>
      ${users.map((user) => `<tr>
        <td>${escapeHtml(user.display_name || user.username)}<br><span class="field-hint">${escapeHtml(user.username)}</span></td>
        <td>${user.role === "admin" ? "管理员" : "普通用户"}</td>
        <td>${escapeHtml(user.department || "未分组")}</td>
        <td>${user.enabled ? "可登录" : "已禁用"}</td>
        <td>${escapeHtml((presets[user.role] || {}).scope || "")}</td>
      </tr>`).join("")}
    </tbody></table>` : emptyTable("暂无用户。");

  const activities = data.activities || [];
  $("#userActivityMeta").textContent = `最近 ${activities.length} 条`;
  $("#userActivityTable").innerHTML = activities.length ? `
    <table><thead><tr><th>时间</th><th>用户</th><th>角色</th><th>操作</th><th>说明</th></tr></thead><tbody>
      ${activities.map((item) => `<tr>
        <td>${escapeHtml(item.time || "")}</td>
        <td>${escapeHtml(item.username || "")}</td>
        <td>${item.role === "admin" ? "管理员" : "普通用户"}</td>
        <td>${escapeHtml(item.action || "")}</td>
        <td>${escapeHtml(item.detail || "")}</td>
      </tr>`).join("")}
    </tbody></table>` : emptyTable("暂无操作记录。");
}

function advancedFilteredItems(sourceItems = state.items) {
  const keyword = ($("#searchKeyword")?.value || "").trim();
  const platform = $("#searchPlatform")?.value || "";
  const risk = $("#searchRisk")?.value || "";
  const sentiment = $("#searchSentiment")?.value || "";
  const analyzeStatus = $("#searchAnalyzeStatus")?.value || "";
  const imageRule = $("#searchImageRule")?.value || "";
  return sourceItems.filter((item) => {
    const haystack = `${item.text || ""} ${item.keyword || ""} ${item.screen_name || ""} ${item.platform_name || ""}`;
    if (keyword && !haystack.includes(keyword)) return false;
    if (platform && item.platform !== platform) return false;
    if (risk && !matchesRiskRule(item, risk)) return false;
    if (sentiment && inferSentiment(item) !== sentiment) return false;
    if (analyzeStatus === "done" && item.analysis_status !== "done") return false;
    if (analyzeStatus === "pending" && ["done", "error"].includes(item.analysis_status)) return false;
    if (analyzeStatus === "error" && item.analysis_status !== "error") return false;
    if (imageRule === "has" && !(item.pics || []).length) return false;
    if (imageRule === "none" && (item.pics || []).length) return false;
    return true;
  });
}

function matchesRiskRule(item, risk) {
  const bucket = riskBucket(item);
  if (risk === "high") return bucket === "高风险";
  if (risk === "medium-high") return bucket === "中高风险";
  if (risk === "medium") return bucket === "中风险";
  if (risk === "low") return bucket === "低风险";
  return true;
}

function renderCollectionSources() {
  const platformCount = state.sources.filter((item) => item.source_kind === "platform").length;
  const applicationCount = state.sources.length - platformCount;
  $("#sourceMeta").textContent = `平台源 ${platformCount} 个，申请源 ${applicationCount} 个`;
  const submit = $("#sourceForm button.primary");
  const formId = $("#sourceId").value;
  const formSource = state.sources.find((entry) => entry.id === formId);
  const canUpdateAsUser = formSource && formSource.source_kind !== "platform" && !["已配置", "已通过"].includes(formSource.status);
  const showUpdate = formId && (state.role === "admin" || canUpdateAsUser);
  if (formId && state.role !== "admin" && !canUpdateAsUser) $("#sourceId").value = "";
  if (submit) submit.textContent = state.role === "admin" ? (showUpdate ? "保存采集源" : "直接配置采集源") : (showUpdate ? "更新申请" : "提交采集申请");
  $("#sourceTable").innerHTML = state.sources.length ? `
    <table><thead><tr><th>平台名称</th><th>类型</th><th>网址</th><th>关键词</th><th>状态</th><th>提交人</th><th>操作</th></tr></thead><tbody>
      ${state.sources.map((item) => `<tr>
        <td><strong>${escapeHtml(item.platform_name)}</strong>${sourceKindBadge(item)}</td>
        <td>${escapeHtml(item.platform_type)}</td><td>${escapeHtml(shortText(item.target_url, 34))}</td>
        <td>${escapeHtml(shortText(item.keywords, 30))}</td><td>${renderSourceStatus(item)}</td><td>${escapeHtml(ownerLabel(item.owner))}</td>
        <td>${renderSourceActions(item)}</td>
      </tr>`).join("")}
    </tbody></table>` : emptyTable("还没有采集源，请先提交采集申请。");
}

function renderSourceStatus(item) {
  const status = item.status || "待审核";
  if (state.role !== "admin" || item.source_kind === "platform") return escapeHtml(status);
  const options = ["待审核", "已通过", "已退回", "已停用", "已配置"];
  return `<select class="inline-select" data-source-status="${escapeHtml(item.id)}">${options.map((option) => `<option value="${escapeHtml(option)}" ${option === status ? "selected" : ""}>${escapeHtml(option)}</option>`).join("")}</select>`;
}

function sourceKindBadge(item) {
  if (item.source_kind === "platform") return "<span class='mini-badge ok'>任务平台</span>";
  if (item.source_kind === "custom" || item.status === "已通过") return "<span class='mini-badge pending'>扩展平台</span>";
  return "";
}

function renderSourceActions(item) {
  const isPlatform = item.source_kind === "platform";
  const isOwner = item.owner === state.user;
  const canEdit = state.role === "admin" || (!isPlatform && isOwner && !["已配置", "已通过"].includes(item.status));
  const canDelete = state.role === "admin" && !isPlatform;
  const actions = [];
  if (canEdit) actions.push(`<button type="button" data-source-edit="${escapeHtml(item.id)}">${state.role === "admin" ? "配置" : "修改申请"}</button>`);
  if (canDelete) actions.push(`<button type="button" class="danger-inline" data-source-delete="${escapeHtml(item.id)}">删除</button>`);
  if (!actions.length) return `<span class="status-empty">${isPlatform ? "系统平台源" : "无可用操作"}</span>`;
  return actions.join("");
}

async function saveCollectionSource(event) {
  event.preventDefault();
  const rawId = $("#sourceId").value;
  const currentSource = state.sources.find((entry) => entry.id === rawId);
  const cannotUpdateAsUser = state.role !== "admin" && currentSource && (
    currentSource.source_kind === "platform" || ["已配置", "已通过"].includes(currentSource.status)
  );
  const id = cannotUpdateAsUser ? "" : rawId;
  if (cannotUpdateAsUser) $("#sourceId").value = "";
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
    if (!id && state.role !== "admin") window.alert("采集申请已提交，等待管理员审核。");
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
  if (state.role !== "admin" && item.source_kind === "platform") {
    window.alert("普通用户不能修改系统采集源，请提交新的采集申请。");
    return;
  }
  if (state.role !== "admin" && ["已配置", "已通过"].includes(item.status)) {
    window.alert("已通过的采集源不能直接修改，请重新提交申请。");
    return;
  }
  $("#sourceId").value = item.id;
  $("#sourcePlatformName").value = item.platform_name || "";
  $("#sourceTargetUrl").value = item.target_url || "";
  $("#sourceAccountName").value = item.account_name || "";
  $("#sourcePlatformType").value = item.platform_type || "新闻网站";
  $("#sourceTimeRange").value = item.time_range || "近两个月";
  $("#sourceKeywords").value = item.keywords || "";
  switchView("collection");
  renderCollectionSources();
}

async function deleteCollectionSource(id) {
  if (state.role !== "admin") {
    window.alert("普通用户没有删减采集源列表的权限。");
    return;
  }
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
  renderCollectionSources();
}

async function updateCollectionSourceStatus(id, status) {
  if (state.role !== "admin") return;
  const item = state.sources.find((entry) => entry.id === id);
  if (!item) return;
  try {
    await fetchJson(`/api/collection-sources/${encodeURIComponent(id)}`, {
      method: "PUT",
      body: JSON.stringify({ ...item, status }),
    });
    await loadCollectionSources();
    renderCollectionSources();
  } catch (error) {
    window.alert(error.message);
  }
}

function renderAdminStatus() {
  $("#taskMeta").textContent = state.status.running ? "任务运行中" : "任务空闲";
  const totalRows = [
    ["运行状态", state.status.running ? (state.status.paused ? "已暂停" : "运行中") : "空闲"],
    ["平台数量", (state.status.selected_platforms || []).length || 0],
    ["累计写入", state.status.current_stats?.inserted || 0],
    ["累计重复", state.status.current_stats?.skipped || 0],
    ["未命中", state.status.current_stats?.unmatched || 0],
    ["丢弃", state.status.current_stats?.discarded || 0],
  ].map(([label, value]) => `<div class="component-row"><span>${label}</span><strong>${value}</strong></div>`).join("");
  const platformStats = state.status.platform_results || {};
  const selected = state.status.selected_platforms || Object.keys(platformStats);
  const platformRows = selected.length ? selected.map((platform) => {
    const stats = platformStats[platform] || {};
    return `<div class="platform-result-row">
      <strong>${escapeHtml(platformLabel(platform))}</strong>
      <span>写入 ${Number(stats.inserted || 0)}</span>
      <span>重复 ${Number(stats.skipped || 0)}</span>
      <span>未命中 ${Number(stats.unmatched || 0)}</span>
      <span>丢弃 ${Number(stats.discarded || 0)}</span>
    </div>`;
  }).join("") : `<p class="status-empty">暂无平台级执行结果。</p>`;
  $("#taskSummaryList").innerHTML = `
    <div class="task-result-total">${totalRows}</div>
    <div class="task-result-platforms">${platformRows}</div>
  `;
  $("#engineStatusText").textContent = state.health?.model_ready ? "已加载" : "待初始化";
  $("#healthStatusMirror").textContent = state.health?.success ? "在线" : "异常";
  $("#statusMeta").textContent = state.health?.success ? `组件 ${Object.keys(state.health.component_status || {}).length} 项` : "状态异常";
  $("#componentStatusList").innerHTML = Object.entries(state.health?.component_status || {}).map(([name, status]) => `<div class="component-row"><span>${escapeHtml(name)}</span><strong>${escapeHtml(status)}</strong></div>`).join("") || `<p class="status-empty">暂无组件状态。</p>`;
}

function renderAdminSettings() {
  if (state.role !== "admin") return;
  renderSourceApplicationsPanel();
  renderKnownPlatformCatalog();
  renderPlatformSettingsCards();
}

function renderSourceApplicationsPanel() {
  const list = (state.platformSettings.source_applications || []).filter((item) => !["已通过", "已配置"].includes(item.status));
  $("#sourceApplicationAlert")?.classList.toggle("is-hidden", !list.length);
  $("#sourceApplicationsPanel").innerHTML = list.length ? list.map((item) => {
    return `<article class="platform-settings-card source-application-card source-application-summary-card">
      <div class="source-application-summary">
        <span>平台名：${escapeHtml(item.platform_name || "未命名平台")}</span>
        <span>提交人：${escapeHtml(ownerLabel(item.owner))}</span>
        <span>提交时间：${escapeHtml(item.created_at || "")}</span>
        <a class="report-link" href="/platform-application?id=${encodeURIComponent(item.id)}" target="_blank">查看详情</a>
      </div>
    </article>`;
  }).join("") : emptyCard("暂无待处理的前台采集申请。");
}

function renderKnownPlatformCatalog() {
  $("#knownPlatformCatalog").innerHTML = (state.platformSettings.known_platforms || []).map((platform) => `
    <article class="catalog-item"><div><h4>${escapeHtml(platform.label)}</h4><p>${escapeHtml(platform.description || "")}</p></div><button type="button" data-add-platform="${escapeHtml(platform.id)}">${platform.added ? "撤销加入" : "加入设置"}</button></article>
  `).join("") || emptyCard("暂无可扩展平台。");
}

function renderPlatformSettingsCards() {
  const entries = Object.values(state.platformSettings.platforms || {});
  $("#settingsStatusText").textContent = `当前共 ${entries.length} 个平台配置`;
  updateSettingsSaveState();
  if (!entries.length) {
    $("#platformSettingsList").innerHTML = emptyCard("暂无平台配置。");
    return;
  }
  if (!entries.some((item) => item.id === state.activeSettingsPlatformId)) state.activeSettingsPlatformId = entries[0].id;
  $("#platformSettingsSelect").innerHTML = entries.map((item) => `<option value="${escapeHtml(item.id)}" ${item.id === state.activeSettingsPlatformId ? "selected" : ""}>${escapeHtml(item.label)}</option>`).join("");
  const config = entries.find((item) => item.id === state.activeSettingsPlatformId) || entries[0];
  const cookieOverrideNote = config.runtime_cookie_override
    ? `<p class="platform-settings-note warning">系统设置中存在 Cookie 覆盖，当前爬虫会优先使用覆盖 Cookie；清空覆盖后才会使用这里保存的 Cookie。</p>`
    : "";
  $("#platformSettingsList").innerHTML = `
    <article class="platform-settings-card">
      <div class="platform-settings-head"><div><h3>${escapeHtml(config.label)}</h3><p class="platform-settings-note">${escapeHtml(config.description || "")}</p></div><span class="mini-badge ${config.available ? "ok" : "pending"}">${config.available ? "已接入" : "待接入"}</span></div>
      <div class="config-grid">
        <div class="field"><label>默认参与爬取</label><div class="toggle-field"><input type="checkbox" data-setting="${escapeHtml(config.id)}" data-field="selected" ${config.selected ? "checked" : ""} ${config.available ? "" : "disabled"}><span>任务启动时默认勾选</span></div></div>
        <div class="field"><label>需要图片</label><div class="toggle-field"><input type="checkbox" data-setting="${escapeHtml(config.id)}" data-field="require_images" ${config.require_images ? "checked" : ""}><span>仅保留满足图片要求的内容</span></div></div>
        <div class="field full"><label>Cookie</label>${cookieOverrideNote}<textarea data-setting="${escapeHtml(config.id)}" data-field="cookie">${escapeHtml(config.cookie || "")}</textarea></div>
        <div class="field full"><label>关键词列表</label><textarea data-setting="${escapeHtml(config.id)}" data-field="keywords">${escapeHtml((config.keywords || []).join("\n"))}</textarea></div>
        <div class="field"><label>每个关键词最多页数</label><input type="number" min="1" max="1000" data-setting="${escapeHtml(config.id)}" data-field="max_pages" value="${escapeHtml(config.max_pages || 10)}"></div>
      </div>
    </article>`;
}

function renderPlatformSettingsCardsV2() {
  const entries = Object.values(state.platformSettings.platforms || {});
  $("#settingsStatusText").textContent = `当前共 ${entries.length} 个平台配置`;
  updateSettingsSaveState();
  if (!entries.length) {
    $("#platformSettingsList").innerHTML = emptyCard("暂无平台配置。");
    return;
  }
  if (!entries.some((item) => item.id === state.activeSettingsPlatformId)) state.activeSettingsPlatformId = entries[0].id;
  $("#platformSettingsSelect").innerHTML = entries.map((item) => `<option value="${escapeHtml(item.id)}" ${item.id === state.activeSettingsPlatformId ? "selected" : ""}>${escapeHtml(item.label)}</option>`).join("");
  const config = entries.find((item) => item.id === state.activeSettingsPlatformId) || entries[0];
  const cookieOverrideNote = config.runtime_cookie_override
    ? `<p class="platform-settings-note warning">系统设置中存在 Cookie 覆盖，当前爬虫会优先使用覆盖 Cookie；清空覆盖后才会使用这里保存的 Cookie。</p>`
    : "";
  $("#platformSettingsList").innerHTML = `
    <article class="platform-settings-card">
      <div class="platform-settings-head"><div><h3>${escapeHtml(config.label)}</h3><p class="platform-settings-note">${escapeHtml(config.description || "")}</p></div><span class="mini-badge ${config.available ? "ok" : "pending"}">${config.available ? "已接入" : "待接入"}</span></div>
      <div class="config-grid">
        <div class="field"><label>默认参与爬取</label><div class="toggle-field"><input type="checkbox" data-setting="${escapeHtml(config.id)}" data-field="selected" ${config.selected ? "checked" : ""} ${config.available ? "" : "disabled"}><span>任务启动时默认勾选</span></div></div>
        <div class="field"><label>需要图片</label><div class="toggle-field"><input type="checkbox" data-setting="${escapeHtml(config.id)}" data-field="require_images" ${config.require_images ? "checked" : ""}><span>仅保留满足图片要求的内容</span></div></div>
        <div class="field full"><label>Cookie</label>${cookieOverrideNote}<textarea data-setting="${escapeHtml(config.id)}" data-field="cookie">${escapeHtml(config.cookie || "")}</textarea></div>
        <div class="field full"><label>关键词列表</label><textarea data-setting="${escapeHtml(config.id)}" data-field="keywords">${escapeHtml((config.keywords || []).join("\n"))}</textarea></div>
        ${"discovery_keywords" in config ? `<div class="field full"><label>发现/搜索关键词</label><textarea data-setting="${escapeHtml(config.id)}" data-field="discovery_keywords">${escapeHtml((config.discovery_keywords || []).join("\n"))}</textarea></div>` : ""}
        ${"forums" in config ? `<div class="field full"><label>贴吧/分区发现源</label><textarea data-setting="${escapeHtml(config.id)}" data-field="forums">${escapeHtml((config.forums || []).join("\n"))}</textarea></div>` : ""}
        ${"recent_days" in config ? `<div class="field"><label>最近天数</label><input type="number" min="1" max="3650" data-setting="${escapeHtml(config.id)}" data-field="recent_days" value="${escapeHtml(config.recent_days || 60)}"></div>` : ""}
        <div class="field"><label>每个关键词最多页数</label><input type="number" min="1" max="1000" data-setting="${escapeHtml(config.id)}" data-field="max_pages" value="${escapeHtml(config.max_pages || 10)}"></div>
        ${"note_time" in config ? `<div class="field"><label>小红书时间范围</label><input type="number" min="0" max="4" data-setting="${escapeHtml(config.id)}" data-field="note_time" value="${escapeHtml(config.note_time || 0)}"></div>` : ""}
      </div>
    </article>`;
}

renderPlatformSettingsCards = renderPlatformSettingsCardsV2;

function updateSettingsSaveState() {
  const button = $("#saveSettingsBtn");
  if (!button) return;
  button.disabled = !state.settingsDirty;
  button.classList.toggle("is-dirty", state.settingsDirty);
}

async function savePlatformSettings() {
  readActivePlatformSettingsIntoState();
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
  const corePlatformIds = new Set(["weibo", "douyin", "tieba", "xhs"]);
  const knownAdded = (state.platformSettings.known_platforms || []).filter((item) => item.added).map((item) => item.id);
  const approvedAdded = Object.values(state.platformSettings.platforms || {})
    .filter((item) => !corePlatformIds.has(item.id) && !(state.platformSettings.known_platforms || []).some((known) => known.id === item.id))
    .map((item) => item.id);
  payload.added_platforms = [...new Set([...knownAdded, ...approvedAdded])];
  try {
    state.platformSettings = await fetchJson("/api/platform-settings", { method: "POST", body: JSON.stringify(payload) });
    state.settingsDirty = false;
    renderAdminSettings();
    renderTaskControl();
    window.alert("平台配置已保存。");
  } catch (error) {
    window.alert(error.message);
  }
}

async function savePlatformSettingsV2() {
  readActivePlatformSettingsIntoState();
  const payload = { added_platforms: [], platforms: {} };
  Object.values(state.platformSettings.platforms || {}).forEach((config) => {
    payload.platforms[config.id] = {
      selected: Boolean(config.selected),
      require_images: Boolean(config.require_images),
      cookie: config.cookie || "",
      keywords: config.keywords || [],
      discovery_keywords: config.discovery_keywords || [],
      forums: config.forums || [],
      recent_days: Number(config.recent_days || 60),
      max_pages: Number(config.max_pages || 10),
      note_time: Number(config.note_time || 0),
    };
  });
  const corePlatformIds = new Set(["weibo", "douyin", "tieba", "xhs"]);
  const knownAdded = (state.platformSettings.known_platforms || []).filter((item) => item.added).map((item) => item.id);
  const approvedAdded = Object.values(state.platformSettings.platforms || {})
    .filter((item) => !corePlatformIds.has(item.id) && !(state.platformSettings.known_platforms || []).some((known) => known.id === item.id))
    .map((item) => item.id);
  payload.added_platforms = [...new Set([...knownAdded, ...approvedAdded])];
  try {
    state.platformSettings = await fetchJson("/api/platform-settings", { method: "POST", body: JSON.stringify(payload) });
    state.settingsDirty = false;
    renderAdminSettings();
    renderTaskControl();
    window.alert("平台配置已保存。");
  } catch (error) {
    window.alert(error.message);
  }
}

savePlatformSettings = savePlatformSettingsV2;

async function reviewPlatformApplication(id, status) {
  const config = {
    cookie: readApplicationField(id, "cookie", "text", ""),
    keywords: readApplicationField(id, "keywords", "text", ""),
    recent_days: Number(readApplicationField(id, "recent_days", "number", 60)),
    max_pages: Number(readApplicationField(id, "max_pages", "number", 10)),
    require_images: readApplicationField(id, "require_images", "checkbox", true),
  };
  try {
    state.platformSettings = await fetchJson(`/api/platform-settings/applications/${encodeURIComponent(id)}/review`, {
      method: "POST",
      body: JSON.stringify({ status, platform_config: config }),
    });
    state.settingsDirty = false;
    await loadCollectionSources();
    renderAdminSettings();
    renderCollectionSources();
    window.alert(status === "approve" ? "申请已同意，平台已加入扩展平台与采集源列表。" : "申请已退回。");
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

function updatePlatformSettingDraft(element) {
  const id = element?.dataset?.setting;
  const field = element?.dataset?.field;
  if (!id || !field || !state.platformSettings.platforms?.[id]) return;
  const value = element.type === "checkbox" ? element.checked : element.value;
  if (field === "keywords" || field === "discovery_keywords" || field === "forums") {
    state.platformSettings.platforms[id][field] = String(value || "").split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  } else if (field === "max_pages" || field === "recent_days" || field === "note_time") {
    state.platformSettings.platforms[id][field] = Number(value || 0);
  } else {
    state.platformSettings.platforms[id][field] = value;
  }
}

function readActivePlatformSettingsIntoState() {
  const activeId = state.activeSettingsPlatformId;
  if (!activeId || !state.platformSettings.platforms?.[activeId]) return;
  $$(`[data-setting="${cssEscape(activeId)}"]`).forEach(updatePlatformSettingDraft);
}

function readSetting(id, field, type, fallback) {
  const el = document.querySelector(`[data-setting="${id}"][data-field="${field}"]`);
  if (!el) return fallback;
  return type === "checkbox" ? el.checked : el.value;
}

function readApplicationField(id, field, type, fallback) {
  const el = document.querySelector(`[data-application="${id}"][data-field="${field}"]`);
  if (!el) return fallback;
  return type === "checkbox" ? el.checked : el.value;
}

function readLines(id, field) {
  return String(readSetting(id, field, "text", "") || "").split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
}

function renderCrawlRules() {
  const box = $("#ruleCards");
  if (!box || state.role !== "admin") return;
  const categories = state.crawlRules?.categories || [];
  box.innerHTML = categories.length
    ? categories.map((category, index) => {
      const expanded = Boolean(state.expandedCrawlRules[index]);
      const itemCount = (category.items || []).length;
      return `
      <article class="admin-card crawl-rule-card ${expanded ? "is-expanded" : ""}">
        <div class="rule-card-head">
          <div>
            <h3>${escapeHtml(category.title)}</h3>
            <p>${itemCount} 个平台规则，默认隐藏详细内容</p>
          </div>
          <button class="rule-toggle-btn" type="button" data-rule-toggle="${index}">${expanded ? "收起" : "展开"}</button>
        </div>
        <div class="rule-platform-list ${expanded ? "" : "is-hidden"}">
          ${(category.items || []).map((item) => `
            <div class="rule-platform-item">
              <div class="rule-platform-head">
                <strong>${escapeHtml(item.label || item.platform || "平台")}</strong>
                <span>${escapeHtml(item.platform || "")}</span>
              </div>
              <ul class="rule-list">
                ${(item.rules || []).map((rule) => `<li>${escapeHtml(rule)}</li>`).join("")}
              </ul>
              ${(item.samples || []).length ? `<div class="chip-list rule-samples">${item.samples.map((sample) => `<span>${escapeHtml(sample)}</span>`).join("")}</div>` : ""}
            </div>
          `).join("")}
        </div>
      </article>
    `;
    }).join("")
    : emptyCard("暂无采集规则配置。");
}

function renderSystemSettings() {
  if (state.role !== "admin" || !$("#systemSettings")) return;
  if (state.systemSettingsDirty) return;
  const settings = state.systemSettings || {};
  const runtime = settings.runtime || {};
  const engineOptions = settings.engine_options || [];
  const cookies = runtime.platform_cookies || {};
  const platforms = settings.platforms || [];
  $("#systemSettingsMeta").textContent = runtime.analysis_engine_file ? "已读取 runtime_config.json" : "未加载";
  $("#systemSettings").innerHTML = `
    <article class="admin-card system-setting-card">
      <div class="system-card-head"><h3>分析引擎</h3><button class="primary" type="button" data-system-save="engine">保存分析引擎</button></div>
      <div class="system-form-grid">
        <label>分析实现文件
          <select id="sysEngineFile">
            ${engineOptions.map((name) => `<option value="${escapeHtml(name)}" ${name === runtime.analysis_engine_file ? "selected" : ""}>${escapeHtml(name)}</option>`).join("")}
          </select>
        </label>
        <label>分析并发数
          <input id="sysAnalysisWorkers" type="number" min="1" max="64" value="${escapeHtml(runtime.analysis_max_workers || 1)}">
        </label>
        <label>单轮采集目标量
          <input id="sysCrawlTarget" type="number" min="1" max="10000" value="${escapeHtml(runtime.crawl_total_target || 200)}">
        </label>
      </div>
      <div class="setting-toggle-list">
        ${renderSettingToggle("sysAutoAnalyze", "自动分析新数据", "爬虫写入 MongoDB 后自动调用多模态分析。", runtime.auto_analyze_crawled_items)}
        ${renderSettingToggle("sysLoadWordVector", "加载词向量模型", "测试时可关闭，减少模型初始化等待时间。", runtime.load_word_vector_model)}
        ${renderSettingToggle("sysStrictRuntime", "严格启动检查", "开启后 MongoDB 或模型依赖异常会阻止后端继续运行。", runtime.strict_runtime)}
      </div>
    </article>
    <article class="admin-card system-setting-card">
      <div class="system-card-head"><div><h3>平台 Cookie 覆盖</h3><p>这里保存到 runtime_config.json，会覆盖平台配置里的 Cookie，适合统一切换测试账号。</p></div><button class="primary" type="button" data-system-save="cookies">保存 Cookie</button></div>
      <div class="cookie-setting-list">
        ${platforms.map((platform) => `
          <label>${escapeHtml(platform.label || platform.id)}
            <textarea data-system-cookie="${escapeHtml(platform.id)}" placeholder="未填写则使用平台配置">${escapeHtml(cookies[platform.id] || "")}</textarea>
          </label>
        `).join("")}
      </div>
    </article>
  `;
  renderSystemMaintenance();
}

function currentAvatarUrl() {
  return state.avatarPendingPreview || state.avatarUrl || "";
}

function renderProfileAvatar(element, fallbackText, imageUrl) {
  if (!element) return;
  element.innerHTML = "";
  element.classList.toggle("has-image", Boolean(imageUrl));
  if (imageUrl) {
    const img = document.createElement("img");
    img.src = imageUrl;
    img.alt = "用户头像";
    element.appendChild(img);
  } else {
    element.textContent = fallbackText;
  }
}

function updateSessionUser(user = {}) {
  state.user = user.username || state.user;
  state.role = user.role === "admin" ? "admin" : state.role;
  state.displayName = user.display_name || state.displayName || state.user;
  state.phone = user.phone || "";
  state.department = user.department || "";
  state.avatarUrl = user.avatar_url || "";
  localStorage.setItem("monitorSession", JSON.stringify({
    username: state.user,
    role: state.role,
    display_name: state.displayName,
    phone: state.phone,
    department: state.department,
    avatar_url: state.avatarUrl,
  }));
}

function renderSettingToggle(id, title, detail, checked) {
  return `<label class="setting-toggle">
    <input id="${id}" type="checkbox" ${checked ? "checked" : ""}>
    <span><strong>${escapeHtml(title)}</strong><em>${escapeHtml(detail)}</em></span>
  </label>`;
}

function renderSystemMaintenance() {
  if (state.role !== "admin" || !$("#systemMaintenance")) return;
  const settings = state.systemSettings || {};
  const runtime = settings.runtime || {};
  const paths = settings.paths || {};
  const database = settings.database || {};
  const collections = database.collections || {};
  $("#systemMaintenance").innerHTML = `
    <div class="system-status-grid">
      <article><span>当前分析文件</span><strong>${escapeHtml(runtime.analysis_engine_path || runtime.analysis_engine_file || "未加载")}</strong></article>
      <article><span>运行配置文件</span><strong>${escapeHtml(paths.runtime_config_file || "")}</strong></article>
      <article><span>MongoDB</span><strong>${escapeHtml(database.mongo_uri || "未配置")}</strong></article>
      <article><span>前端目录</span><strong>${escapeHtml(paths.frontend_dir || "")}</strong></article>
      <article><span>爬虫目录</span><strong>${escapeHtml(paths.crawler_dir || "")}</strong></article>
      <article><span>平台集合</span><strong>${escapeHtml(Object.entries(collections).map(([platform, name]) => `${platform}:${name}`).join(" / "))}</strong></article>
    </div>
  `;
}

function buildSystemSettingsPayload(section = "all") {
  const runtime = state.systemSettings?.runtime || {};
  const payload = {
    analysis_engine_file: section === "cookies" ? (runtime.analysis_engine_file || "") : ($("#sysEngineFile")?.value || runtime.analysis_engine_file || ""),
    analysis_max_workers: section === "cookies" ? Number(runtime.analysis_max_workers || 1) : Number($("#sysAnalysisWorkers")?.value || runtime.analysis_max_workers || 1),
    crawl_total_target: section === "cookies" ? Number(runtime.crawl_total_target || 200) : Number($("#sysCrawlTarget")?.value || runtime.crawl_total_target || 200),
    auto_analyze_crawled_items: section === "cookies" ? Boolean(runtime.auto_analyze_crawled_items) : Boolean($("#sysAutoAnalyze")?.checked),
    load_word_vector_model: section === "cookies" ? Boolean(runtime.load_word_vector_model) : Boolean($("#sysLoadWordVector")?.checked),
    strict_runtime: section === "cookies" ? Boolean(runtime.strict_runtime) : Boolean($("#sysStrictRuntime")?.checked),
    platform_cookies: { ...(runtime.platform_cookies || {}) },
  };
  if (section !== "engine") {
    $$("[data-system-cookie]").forEach((textarea) => {
      payload.platform_cookies[textarea.dataset.systemCookie] = textarea.value;
    });
  }
  return payload;
}

function applyRuntimeCookiesToPlatformState(cookies = {}) {
  Object.values(state.platformSettings.platforms || {}).forEach((config) => {
    const override = String(cookies[config.id] || "").trim();
    config.runtime_cookie_override = override;
    config.effective_cookie = override || config.cookie || "";
  });
}

async function saveSystemSettings(section = "all") {
  const payload = buildSystemSettingsPayload(section);
  try {
    const data = await fetchJson("/api/admin/system-settings", {
      method: "PUT",
      body: JSON.stringify(payload),
    });
    state.systemSettings = { ...state.systemSettings, ...data };
    state.systemSettingsDirty = false;
    if (section === "cookies") {
      applyRuntimeCookiesToPlatformState(data.runtime?.platform_cookies || {});
      renderAdminSettings();
      renderTaskControl();
    }
    window.alert(section === "cookies" ? "平台 Cookie 覆盖已保存。" : "分析引擎设置已保存。");
    await refreshAll();
  } catch (error) {
    window.alert(error.message);
  }
}

async function resetAnalysisEngine() {
  if (!window.confirm("确定要重置分析引擎吗？下次分析会按当前配置重新加载模型。")) return;
  try {
    const data = await fetchJson("/api/admin/system-settings/reset-engine", { method: "POST", body: "{}" });
    state.systemSettings = { ...state.systemSettings, ...data };
    state.systemSettingsDirty = false;
    window.alert("分析引擎已重置。");
    await refreshAll();
  } catch (error) {
    window.alert(error.message);
  }
}

async function refreshDatabaseWorkbench() {
  if (state.role !== "admin") return;
  await loadDatabaseOverview();
  if (state.database.selectedDb) await loadDatabaseCollections(state.database.selectedDb);
  if (state.database.selectedCollection) {
    await loadDatabaseDocuments();
    await loadDatabaseIndexes();
  }
  renderDatabaseWorkbench();
}

async function selectDatabase(dbName) {
  state.database.selectedDb = dbName;
  state.database.selectedCollection = "";
  state.database.documents = [];
  state.database.indexes = [];
  state.database.skip = 0;
  await loadDatabaseCollections(dbName);
  renderDatabaseWorkbench();
}

async function selectDatabaseCollection(dbName, collectionName) {
  state.database.selectedDb = dbName;
  state.database.selectedCollection = collectionName;
  state.database.skip = 0;
  state.database.editingId = "";
  await loadDatabaseCollections(dbName);
  await loadDatabaseDocuments();
  await loadDatabaseIndexes();
  renderDatabaseWorkbench();
}

async function queryDatabaseDocuments() {
  state.database.skip = 0;
  await loadDatabaseDocuments();
  renderDatabaseWorkbench();
}

function resetDatabaseQuery() {
  state.database.filterText = "{}";
  state.database.sortText = "{ \"_id\": -1 }";
  state.database.limit = 20;
  state.database.skip = 0;
  loadDatabaseDocuments().then(renderDatabaseWorkbench);
}

async function pageDatabaseDocuments(direction) {
  const limit = state.database.limit || 20;
  state.database.skip = Math.max(0, (state.database.skip || 0) + direction * limit);
  await loadDatabaseDocuments();
  renderDatabaseWorkbench();
}

async function changeDatabaseLimit(value) {
  const nextLimit = [10, 20, 50, 100].includes(Number(value)) ? Number(value) : 20;
  state.database.limit = nextLimit;
  state.database.skip = 0;
  await loadDatabaseDocuments();
  renderDatabaseWorkbench();
}

function toggleDatabaseCollapsed(dbName) {
  state.collapsedDatabases[dbName] = !state.collapsedDatabases[dbName];
  renderDatabaseTree();
}

function openDatabaseModal() {
  $("#dbModal")?.classList.remove("is-hidden");
}

function closeDatabaseModal() {
  $("#dbModal")?.classList.add("is-hidden");
  $("#dbEditorMessage").textContent = "";
}

function newDatabaseDocument(render = true) {
  if (!state.database.selectedCollection) {
    window.alert("请先选择集合。");
    return;
  }
  state.database.editingId = "";
  const editor = $("#dbDocumentEditor");
  if (editor) editor.value = "{\n  \"field\": \"value\"\n}";
  $("#dbEditorTitle").textContent = "新增文档";
  $("#dbSaveDocumentBtn").textContent = "插入文档";
  $("#dbEditorMessage").textContent = "";
  openDatabaseModal();
  if (render) renderDatabaseWorkbench();
}

function clearDatabaseEditor() {
  state.database.editingId = "";
  $("#dbDocumentEditor").value = "";
  $("#dbEditorTitle").textContent = "新增文档";
  $("#dbSaveDocumentBtn").textContent = "插入文档";
  $("#dbEditorMessage").textContent = "";
}

function editDatabaseDocument(docId) {
  const doc = state.database.documents.find((item) => String(item._id) === String(docId));
  if (!doc) return;
  state.database.editingId = String(doc._id);
  $("#dbDocumentEditor").value = JSON.stringify(doc, null, 2);
  $("#dbEditorTitle").textContent = `编辑文档 ${shortText(docId, 10)}`;
  $("#dbSaveDocumentBtn").textContent = "保存修改";
  $("#dbEditorMessage").textContent = "";
  openDatabaseModal();
}

async function saveDatabaseDocument() {
  if (!state.database.selectedDb || !state.database.selectedCollection) {
    window.alert("请先选择集合。");
    return;
  }
  const text = $("#dbDocumentEditor")?.value || "";
  let document;
  try {
    document = JSON.parse(text || "{}");
  } catch (error) {
    $("#dbEditorMessage").textContent = `JSON 格式错误：${error.message}`;
    return;
  }
  const editingId = state.database.editingId;
  try {
    const url = editingId ? `/api/admin/database/documents/${encodeURIComponent(editingId)}` : "/api/admin/database/documents";
    await fetchJson(url, {
      method: editingId ? "PUT" : "POST",
      body: JSON.stringify({
        db: state.database.selectedDb,
        collection: state.database.selectedCollection,
        document,
      }),
    });
    $("#dbEditorMessage").textContent = editingId ? "文档已保存。" : "文档已插入。";
    closeDatabaseModal();
    await loadDatabaseDocuments();
    await loadDatabaseCollections(state.database.selectedDb);
    await loadDatabaseOverview();
    renderDatabaseWorkbench();
  } catch (error) {
    $("#dbEditorMessage").textContent = error.message;
  }
}

async function deleteDatabaseDocument(docId) {
  if (!window.confirm("确定删除该文档吗？此操作不可撤销。")) return;
  try {
    await fetchJson(`/api/admin/database/documents/${encodeURIComponent(docId)}`, {
      method: "DELETE",
      body: JSON.stringify({ db: state.database.selectedDb, collection: state.database.selectedCollection }),
    });
    if (state.database.editingId === docId) clearDatabaseEditor();
    await loadDatabaseDocuments();
    await loadDatabaseCollections(state.database.selectedDb);
    await loadDatabaseOverview();
    renderDatabaseWorkbench();
  } catch (error) {
    window.alert(error.message);
  }
}

async function clearDatabaseDocuments() {
  if (!state.database.selectedDb || !state.database.selectedCollection) return;
  const target = `${state.database.selectedDb}.${state.database.selectedCollection}`;
  const confirmText = window.prompt(`将删除 ${target} 中的全部文档，但保留集合和索引。请输入 CLEAR 确认：`);
  if (confirmText !== "CLEAR") return;
  try {
    const data = await fetchJson("/api/admin/database/documents", {
      method: "DELETE",
      body: JSON.stringify({ db: state.database.selectedDb, collection: state.database.selectedCollection }),
    });
    window.alert(`已删除 ${data.deleted || 0} 条文档。`);
    state.database.skip = 0;
    await loadDatabaseDocuments();
    await loadDatabaseCollections(state.database.selectedDb);
    await loadDatabaseOverview();
    renderDatabaseWorkbench();
  } catch (error) {
    window.alert(error.message);
  }
}

async function createDatabaseFromRoot() {
  const dbName = window.prompt("请输入新数据库名称");
  if (!dbName) return;
  const collection = window.prompt("MongoDB 创建数据库需要同时创建第一个集合，请输入集合名称", "default_collection");
  if (!collection) return;
  await createDatabaseCollection(dbName, collection);
}

async function createDatabaseCollection(dbName = state.database.selectedDb, collectionName = "") {
  if (!dbName) return;
  const collection = collectionName || window.prompt(`请输入 ${dbName} 下的新集合名称`);
  if (!collection) return;
  try {
    await fetchJson("/api/admin/database/collections", {
      method: "POST",
      body: JSON.stringify({ db: dbName, collection }),
    });
    state.database.selectedDb = dbName;
    state.database.selectedCollection = collection;
    await refreshDatabaseWorkbench();
  } catch (error) {
    window.alert(error.message);
  }
}

async function dropDatabase(dbName) {
  if (!dbName) return;
  const target = dbName;
  const confirmText = window.prompt(`删除数据库会移除其中全部集合和文档。请输入 ${target} 确认删除：`);
  if (confirmText !== target) return;
  try {
    await fetchJson("/api/admin/database/databases", {
      method: "DELETE",
      body: JSON.stringify({ db: dbName }),
    });
    if (state.database.selectedDb === dbName) {
      state.database.selectedDb = "test";
      state.database.selectedCollection = "";
      state.database.documents = [];
      state.database.indexes = [];
    }
    await refreshDatabaseWorkbench();
  } catch (error) {
    window.alert(error.message);
  }
}

async function dropDatabaseCollection(dbName = state.database.selectedDb, collectionName = state.database.selectedCollection) {
  if (!dbName || !collectionName) {
    window.alert("请先选择要删除的集合。");
    return;
  }
  const target = `${dbName}.${collectionName}`;
  const confirmText = window.prompt(`删除集合会移除其中全部文档。请输入 ${target} 确认删除：`);
  if (confirmText !== target) return;
  try {
    await fetchJson("/api/admin/database/collections", {
      method: "DELETE",
      body: JSON.stringify({ db: dbName, collection: collectionName }),
    });
    if (state.database.selectedDb === dbName && state.database.selectedCollection === collectionName) {
      state.database.selectedCollection = "";
      state.database.documents = [];
      state.database.indexes = [];
    }
    await refreshDatabaseWorkbench();
  } catch (error) {
    window.alert(error.message);
  }
}

function renderDatabaseWorkbench() {
  if (state.role !== "admin" || !$("#databaseTree")) return;
  renderDatabaseTree();
  renderDatabaseCollections();
  renderDatabaseDocuments();
  renderDatabaseIndexes();
}

function renderDatabaseTree() {
  const tree = $("#databaseTree");
  if (!tree) return;
  const keyword = ($("#dbTreeSearch")?.value || "").trim().toLowerCase();
  const databases = state.database.databases || [];
  const root = `<div class="db-root-row ${state.databaseRootCollapsed ? "is-collapsed" : ""}">
    <button type="button" class="db-root-main" data-db-root-toggle><span class="tree-caret">${state.databaseRootCollapsed ? "▸" : "▾"}</span><span class="tree-icon">▣</span><span>localhost:27017</span></button>
    <button type="button" class="db-icon-btn" title="新增数据库" data-db-root-add>+</button>
  </div>`;
  if (state.databaseRootCollapsed) {
    tree.innerHTML = root;
    return;
  }
  const body = databases.length ? databases.map((db) => {
    const collections = (db.collections || []).filter((collection) => {
      const haystack = `${db.name} ${collection.name}`.toLowerCase();
      return !keyword || haystack.includes(keyword);
    });
    if (keyword && !collections.length && !db.name.toLowerCase().includes(keyword)) return "";
    const collapsed = Boolean(state.collapsedDatabases[db.name]);
    const isSystemDb = ["admin", "config", "local"].includes(db.name);
    return `<div class="db-tree-db">
      <div class="db-node-row ${db.name === state.database.selectedDb && !state.database.selectedCollection ? "is-active" : ""}">
        <button type="button" class="db-toggle" data-db-toggle="${escapeHtml(db.name)}">${collapsed ? "▸" : "▾"}</button>
        <button type="button" class="db-node-main" data-db-name="${escapeHtml(db.name)}"><span class="tree-icon">●</span><span>${escapeHtml(db.name)}</span></button>
        <button type="button" class="db-icon-btn" title="新增集合" data-db-create-collection="${escapeHtml(db.name)}">+</button>
        <button type="button" class="db-icon-btn danger" title="删除数据库" ${isSystemDb ? "disabled" : ""} data-db-drop="${escapeHtml(db.name)}">■</button>
      </div>
      <div class="db-tree-collections ${collapsed ? "is-collapsed" : ""}">
        ${collections.map((collection) => `<div class="db-node-row collection-row ${db.name === state.database.selectedDb && collection.name === state.database.selectedCollection ? "is-active" : ""}">
          <button type="button" class="db-node-main" data-db-name="${escapeHtml(db.name)}" data-db-collection="${escapeHtml(collection.name)}"><span class="tree-icon">▣</span><span>${escapeHtml(collection.name)}</span></button>
          <span class="db-count-chip" title="文档数量">${Number(collection.documents || collection.document_count || 0).toLocaleString()}</span>
          <button type="button" class="db-icon-btn danger" title="删除集合" ${isSystemDb ? "disabled" : ""} data-db-name="${escapeHtml(db.name)}" data-db-drop-collection="${escapeHtml(collection.name)}">■</button>
        </div>`).join("")}
      </div>
    </div>`;
  }).join("") : emptyTable("未连接到 MongoDB 或暂无数据库。");
  tree.innerHTML = root + `<div class="db-root-children">${body}</div>`;
}

function renderDatabaseCollections() {
  const box = $("#databaseCollectionsPanel");
  if (!box) return;
  const dbName = state.database.selectedDb || "未选择";
  $("#databaseTitle").textContent = state.database.selectedCollection ? `${dbName}.${state.database.selectedCollection}` : `${dbName} 数据库`;
  $("#databaseMeta").textContent = state.database.selectedCollection ? `共 ${state.database.total || 0} 条匹配文档` : "集合概览、存储大小、文档数和索引数";
  const collections = state.database.collections || [];
  box.classList.toggle("is-hidden", Boolean(state.database.selectedCollection));
  box.innerHTML = `<div class="db-table-wrap">
    <table class="db-table">
      <thead><tr><th>Collection name</th><th>Documents</th><th>Storage size</th><th>Data size</th><th>Avg. document size</th><th>Indexes</th><th>Total index size</th></tr></thead>
      <tbody>${collections.length ? collections.map((collection) => `<tr data-open-db="${escapeHtml(dbName)}" data-open-collection="${escapeHtml(collection.name)}">
        <td><button type="button" data-open-db="${escapeHtml(dbName)}" data-open-collection="${escapeHtml(collection.name)}">${escapeHtml(collection.name)}</button></td>
        <td>${collection.documents || 0}</td>
        <td>${formatBytes(collection.storage_size)}</td>
        <td>${formatBytes(collection.data_size)}</td>
        <td>${formatBytes(collection.avg_document_size)}</td>
        <td>${collection.indexes || 0}</td>
        <td>${formatBytes(collection.total_index_size)}</td>
      </tr>`).join("") : `<tr><td colspan="7">暂无集合。</td></tr>`}</tbody>
    </table>
  </div>`;
}

function renderDatabaseDocuments() {
  const box = $("#databaseDocumentsPanel");
  if (!box) return;
  box.classList.toggle("is-hidden", !state.database.selectedCollection);
  if (!state.database.selectedCollection) {
    box.innerHTML = "";
    return;
  }
  const docs = state.database.documents || [];
  const skip = state.database.skip || 0;
  const limit = state.database.limit || 20;
  box.innerHTML = `${renderDatabaseCollectionHeader()}${renderDatabaseDocumentsPanel(docs, skip, limit)}`;
}

function renderDatabaseCollectionHeader() {
  const db = state.database.selectedDb || "";
  const collection = state.database.selectedCollection || "";
  return `<div class="db-compass-head">
    <div class="db-breadcrumb"><span>localhost:27017</span><span>›</span><span>${escapeHtml(db)}</span><span>›</span><strong>${escapeHtml(collection)}</strong></div>
  </div>`;
}

function renderDatabaseDocumentsPanel(docs, skip, limit) {
  return `<div class="db-filter-shell">
    <label class="db-filter-input"><span>Filter</span><textarea id="dbFilterInput" spellcheck="false" placeholder="{ }">${escapeHtml(state.database.filterText || "{}")}</textarea></label>
    <div class="db-filter-actions"><button id="dbResetQueryBtn" type="button" data-db-reset ${isDatabaseFilterEmpty() ? "disabled" : ""}>Reset</button><button class="primary" type="button" data-db-query>Find</button></div>
  </div>
  <div class="db-doc-actions">
    <div class="db-left-actions"><button class="primary split" type="button" data-db-add-document>＋ ▾</button><button type="button" class="danger" data-db-clear-documents title="删除全部 data">▣</button></div>
    <div class="db-page-actions"><select id="dbLimitSelect" title="当前页可滚动查看的数据条数">${[10, 20, 50, 100].map((value) => `<option value="${value}" ${Number(limit) === value ? "selected" : ""}>${value}</option>`).join("")}</select><span>${(state.database.total || 0) ? `${skip + 1} - ${Math.min(skip + limit, state.database.total || 0)} of ${state.database.total || 0}` : "0 - 0 of 0"}</span><button type="button" data-db-query>⟳</button><button type="button" ${skip <= 0 ? "disabled" : ""} data-db-prev>‹</button><button type="button" ${skip + limit >= (state.database.total || 0) ? "disabled" : ""} data-db-next>›</button></div>
  </div>
  <div class="db-doc-list ${state.database.viewMode === "json" ? "is-json-view" : ""}">${docs.length ? docs.map((doc) => renderDatabaseDocument(doc)).join("") : emptyTable("当前查询没有文档。")}</div>`;
}

function isDatabaseFilterEmpty() {
  const value = String(state.database.filterText || "").trim();
  return !value || value === "{}";
}

function renderDatabaseQueryButtons() {
  const reset = $("#dbResetQueryBtn");
  if (reset) reset.disabled = isDatabaseFilterEmpty();
}

function renderDatabaseDocument(doc) {
  const docId = String(doc._id || "");
  return `<article class="db-document">
    <div class="db-document-head"><strong>_id: ${escapeHtml(docId)}</strong><div><button type="button" data-db-edit="${escapeHtml(docId)}">编辑</button><button type="button" class="danger" data-db-delete="${escapeHtml(docId)}">删除</button></div></div>
    <div class="db-document-tree">${renderDocumentTree(doc)}</div>
  </article>`;
}

function renderDocumentTree(value, depth = 0, keyName = "") {
  if (Array.isArray(value)) {
    return value.map((item, index) => renderDocumentTreeRow(String(index), item, depth)).join("");
  }
  if (value && typeof value === "object") {
    return Object.entries(value).map(([key, item]) => renderDocumentTreeRow(key, item, depth)).join("");
  }
  return `<span class="db-value">${formatTreeValue(value)}</span>`;
}

function renderDocumentTreeRow(key, value, depth) {
  const complex = value && typeof value === "object";
  const type = Array.isArray(value) ? "Array" : complex ? "Object" : "";
  const summary = Array.isArray(value) ? `[${value.length}]` : complex ? "Object" : formatTreeValue(value);
  if (!complex) {
    return `<div class="db-field-row" style="--depth:${depth}"><span class="db-field-spacer"></span><strong>${escapeHtml(key)}</strong><span>:</span><span class="db-value">${summary}</span></div>`;
  }
  return `<details class="db-field-group" style="--depth:${depth}">
    <summary><span class="db-field-caret">▶</span><strong>${escapeHtml(key)}</strong><span>:</span><span class="db-type">${escapeHtml(type)}</span><span class="db-muted">${escapeHtml(summary)}</span></summary>
    <div class="db-field-children">${renderDocumentTree(value, depth + 1)}</div>
  </details>`;
}

function formatTreeValue(value) {
  if (typeof value === "string") return `<span class="db-string">"${escapeHtml(value)}"</span>`;
  if (typeof value === "number") return `<span class="db-number">${value}</span>`;
  if (typeof value === "boolean") return `<span class="db-boolean">${value}</span>`;
  if (value === null || value === undefined) return `<span class="db-null">null</span>`;
  return escapeHtml(String(value));
}

function renderDatabaseIndexes() {
}

function renderDatabaseIndexesHtml() {}

function formatBytes(value) {
  const num = Number(value) || 0;
  if (num < 1024) return `${num} B`;
  if (num < 1024 * 1024) return `${(num / 1024).toFixed(2)} kB`;
  return `${(num / 1024 / 1024).toFixed(2)} MB`;
}

function renderStaticAdminPages() {
}

function filteredItems() {
  const quickFiltered = state.items.filter((item) => {
    if (["weibo", "douyin", "tieba", "xhs"].includes(state.feedFilter)) return item.platform === state.feedFilter;
    if (state.feedFilter === "high") return riskScore(item) >= 80;
    if (state.feedFilter === "recent") return isWithinRecentDays(item.created_at, 60);
    return true;
  });
  return advancedFilteredItems(quickFiltered);
}

function limitedMonitorItems(list) {
  if (state.monitorLimit === "all") return list;
  const limit = Number(state.monitorLimit);
  return Number.isFinite(limit) ? list.slice(0, limit) : list;
}

function highRiskItems() {
  return state.items.filter((item) => riskScore(item) >= 80).slice().sort((a, b) => riskScore(b) - riskScore(a));
}

function riskAnalysisItems() {
  return state.items
    .filter((item) => matchesRiskAnalysisFilter(item, state.riskAnalysisFilter))
    .slice()
    .sort((a, b) => riskScore(b) - riskScore(a));
}

function matchesRiskAnalysisFilter(item, filter) {
  const score = riskScore(item);
  if (!Number.isFinite(score)) return false;
  if (filter === "high") return score >= 80;
  if (filter === "medium-high") return score >= 60 && score < 80;
  if (filter === "medium") return score >= 40 && score < 60;
  return true;
}

function riskFilterLabel(filter) {
  return { all: "全部风险", medium: "中风险", "medium-high": "中高风险", high: "高风险" }[filter] || "中高风险";
}

function watchIdSet() {
  const ids = new Set();
  state.watchlist.forEach((item) => {
    if (item._id) ids.add(String(item._id));
    if (item.id) ids.add(String(item.id));
  });
  return ids;
}

function itemDocId(item) {
  return String(item._id || item.id || "");
}

function isWatched(item) {
  const ids = watchIdSet();
  return ids.has(String(item._id || "")) || ids.has(String(item.id || ""));
}

async function toggleWatchItem(docId) {
  if (!docId) return;
  const tracked = watchIdSet().has(String(docId));
  try {
    const data = await fetchJson(`/api/watchlist${tracked ? `/${encodeURIComponent(docId)}` : ""}`, {
      method: tracked ? "DELETE" : "POST",
      body: tracked ? undefined : JSON.stringify({ id: docId }),
    });
    state.watchlist = data.items || [];
    state.watchTotal = data.total || state.watchlist.length;
    renderMonitor();
    renderTracking();
    renderRiskAnalysis();
  } catch (error) {
    window.alert(error.message);
  }
}

function renderItem(item, options = {}) {
  const score = riskScore(item);
  const reasons = item.analysis?.summary?.reasons || [];
  const docId = itemDocId(item);
  const watched = isWatched(item);
  return `<article class="weibo">
    <div class="card-head"><div class="user-head"><span class="avatar">${escapeHtml(getAvatarText(item.screen_name))}</span><div class="user-copy"><strong>${escapeHtml(item.screen_name || "未知用户")}</strong></div></div><div><div class="meta"><span class="platform-chip">${platformLabel(item.platform)}</span><span>${escapeHtml(item.created_at || "")}</span><span>情感：${inferSentiment(item)}</span><span>${inferRiskType(item)}</span></div></div><div class="risk ${scoreLevelClass(score)}"><span>${riskBucket(item)}</span><strong>${Number.isFinite(score) ? score.toFixed(1) : "--"}</strong></div></div>
    <div class="card-actions"><button type="button" class="${watched ? "secondary" : "primary"}" data-watch-toggle="${escapeHtml(docId)}">${watched ? "取消追踪" : "加入追踪"}</button></div>
    <p class="text">${escapeHtml(item.text || "")}</p>
    ${renderItemPics(item)}
    <div class="reason-list">${reasons.length ? reasons.slice(0, 4).map((reason) => `<span>${escapeHtml(reason)}</span>`).join("") : `<span>${escapeHtml(item.analysis_status || "待分析")}</span>`}</div>
    <a class="report-link" href="/report?id=${encodeURIComponent(docId)}" target="_blank">查看详情</a>
  </article>`;
}

function renderItemPics(item) {
  const pics = (item.pics || [])
    .map((pic) => typeof pic === "string" ? { url: pic, path: pic } : pic)
    .filter((pic) => pic && pic.url);
  if (!pics.length) return "";
  return `<div class="pics">${pics.slice(0, 6).map((pic, index) => `
    <a href="${escapeHtml(pic.url)}" target="_blank" rel="noreferrer">
      <img src="${escapeHtml(pic.url)}" alt="${escapeHtml(`post image ${index + 1}`)}" loading="lazy">
    </a>
  `).join("")}</div>`;
}

function renderCompactRows(list) {
  return list.length ? `<table><thead><tr><th>平台</th><th>内容摘要</th><th>风险等级</th><th>时间</th><th>操作</th></tr></thead><tbody>${list.map((item) => {
    const docId = itemDocId(item);
    return `<tr><td>${platformLabel(item.platform)}</td><td>${escapeHtml(shortText(item.text, 80))}</td><td>${riskBucket(item)}</td><td>${escapeHtml(item.created_at || "")}</td><td><a class="table-action-link" href="/report?id=${encodeURIComponent(docId)}" target="_blank">查看详情</a></td></tr>`;
  }).join("")}</tbody></table>` : emptyTable("当前暂无高风险舆情。");
}

function renderBars(counts, total) {
  const entries = Object.entries(counts).sort((a, b) => b[1] - a[1]);
  return entries.length ? entries.map(([label, value]) => `<div class="bar-row"><div class="bar-head"><span>${escapeHtml(label)}</span><strong>${value}</strong></div><div class="bar-track"><div class="bar-fill" style="width:${Math.max(4, value / total * 100)}%"></div></div></div>`).join("") : "<p class='status-empty'>暂无统计数据。</p>";
}


function renderDonutChart(counts) {
  const entries = Object.entries(counts).filter(([, value]) => value > 0).sort((a, b) => b[1] - a[1]);
  const total = entries.reduce((sum, [, value]) => sum + value, 0);
  if (!total) return "<p class='status-empty'>暂无统计数据。</p>";
  const colors = ["#2f7df6", "#14b889", "#ffb020", "#8b5cf6", "#19b7d6", "#ef5da8", "#64748b"];
  let offset = 0;
  const segments = entries.map(([, value], index) => {
    const percent = value / total * 100;
    const circle = `<circle class="donut-segment" r="15.9155" cx="18" cy="18" fill="transparent" stroke="${colors[index % colors.length]}" stroke-width="6" stroke-dasharray="${percent} ${100 - percent}" stroke-dashoffset="${-offset}" />`;
    offset += percent;
    return circle;
  }).join("");
  const legend = entries.map(([label, value], index) => {
    const percent = Math.round(value / total * 100);
    return `<div class="chart-legend-row"><span class="legend-dot" style="background:${colors[index % colors.length]}"></span><strong>${escapeHtml(label)}</strong><em>${value} 条</em><span>${percent}%</span></div>`;
  }).join("");
  return `<div class="donut-wrap"><svg viewBox="0 0 36 36" class="donut-svg" role="img" aria-label="分布图">${segments}<circle r="10" cx="18" cy="18" fill="#fff"></circle><text x="18" y="17.5" text-anchor="middle" class="donut-total">${total}</text><text x="18" y="22.5" text-anchor="middle" class="donut-unit">条</text></svg><div class="chart-legend">${legend}</div></div>`;
}

function renderLineChart(points) {
  if (!points.length) return "<p class='status-empty'>暂无趋势数据。</p>";
  const width = 760;
  const height = 260;
  const padding = { left: 48, right: 22, top: 20, bottom: 42 };
  const maxValue = Math.max(1, ...points.map((point) => point.value));
  const xStep = points.length > 1 ? (width - padding.left - padding.right) / (points.length - 1) : 0;
  const y = (value) => padding.top + (maxValue - value) / maxValue * (height - padding.top - padding.bottom);
  const pathData = points.map((point, index) => `${index ? "L" : "M"} ${padding.left + index * xStep} ${y(point.value)}`).join(" ");
  const areaPath = `${pathData} L ${padding.left + (points.length - 1) * xStep} ${height - padding.bottom} L ${padding.left} ${height - padding.bottom} Z`;
  const grid = [0, 0.25, 0.5, 0.75, 1].map((ratio) => {
    const value = Math.round(maxValue * (1 - ratio));
    const gy = padding.top + ratio * (height - padding.top - padding.bottom);
    return `<g><line x1="${padding.left}" y1="${gy}" x2="${width - padding.right}" y2="${gy}" class="line-grid"></line><text x="${padding.left - 10}" y="${gy + 4}" text-anchor="end" class="line-axis">${value}</text></g>`;
  }).join("");
  const dots = points.map((point, index) => {
    const x = padding.left + index * xStep;
    const cy = y(point.value);
    return `<g><circle cx="${x}" cy="${cy}" r="4" class="line-dot"></circle><title>${escapeHtml(point.label)}：${point.value} 条</title></g>`;
  }).join("");
  const labels = points.map((point, index) => {
    if (points.length > 8 && index % 2 === 1) return "";
    const x = padding.left + index * xStep;
    return `<text x="${x}" y="${height - 15}" text-anchor="middle" class="line-axis">${escapeHtml(point.shortLabel)}</text>`;
  }).join("");
  return `<svg class="line-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="每日新增舆情数据变化"><path d="${areaPath}" class="line-area"></path>${grid}<line x1="${padding.left}" y1="${height - padding.bottom}" x2="${width - padding.right}" y2="${height - padding.bottom}" class="line-base"></line><path d="${pathData}" class="line-path"></path>${dots}${labels}</svg>`;
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

function dailyTrend(list, days = 14) {
  const now = new Date();
  const dayKeys = Array.from({ length: days }, (_, index) => {
    const date = new Date(now);
    date.setHours(0, 0, 0, 0);
    date.setDate(date.getDate() - (days - 1 - index));
    const key = date.toISOString().slice(0, 10);
    return {
      key,
      label: `${date.getMonth() + 1}/${date.getDate()}`,
      shortLabel: `${date.getMonth() + 1}-${date.getDate()}`,
      value: 0,
    };
  });
  const lookup = Object.fromEntries(dayKeys.map((day) => [day.key, day]));
  list.forEach((item) => {
    const key = itemDateKey(item);
    if (lookup[key]) lookup[key].value += 1;
  });
  return dayKeys;
}

function itemDateKey(item) {
  const raw = item.created_at || item.time || item.publish_time || item.date || "";
  const normalized = String(raw).replace(/\./g, "-").replace(/\//g, "-").replace(" ", "T");
  const parsed = Date.parse(normalized);
  if (Number.isFinite(parsed)) return new Date(parsed).toISOString().slice(0, 10);
  const matched = String(raw).match(/\d{4}-\d{1,2}-\d{1,2}/);
  if (!matched) return "";
  return matched[0].split("-").map((part, index) => index ? part.padStart(2, "0") : part).join("-");
}

function riskScore(item) {
  return normalizeRiskScore(item.analysis?.summary?.total_score);
}

function normalizeRiskScore(value) {
  const score = Number(value);
  if (!Number.isFinite(score)) return NaN;
  return score > 0 && score <= 1 ? score * 100 : score;
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

function cssEscape(value) {
  if (globalThis.CSS?.escape) return globalThis.CSS.escape(String(value));
  return String(value).replace(/["\\]/g, "\\$&");
}
