const tg = window.Telegram?.WebApp;

const statusChip = document.getElementById("statusChip");
const statusTitle = document.getElementById("statusTitle");
const statusSubtitle = document.getElementById("statusSubtitle");
const stateHint = document.getElementById("stateHint");
const connectBtn = document.getElementById("connectBtn");
const connectHint = document.getElementById("connectHint");
const onboardingHelpBtn = document.getElementById("onboardingHelpBtn");
const openAgainBtn = document.getElementById("openAgainBtn");
const checkBtn = document.getElementById("checkBtn");
const disconnectBtn = document.getElementById("disconnectBtn");
const installBtn = document.getElementById("installBtn");
const freeAccessValue = document.getElementById("freeAccessValue");
const rewardStatus = document.getElementById("rewardStatus");
const rewardTimer = document.getElementById("rewardTimer");
const watchAdBtn = document.getElementById("watchAdBtn");
const claimAccessBtn = document.getElementById("claimAccessBtn");
const refLinkInput = document.getElementById("refLink");
const userLine = document.getElementById("userLine");
const copyRefBtn = document.getElementById("copyRefBtn");
const timeLeftValue = document.getElementById("timeLeftValue");
const tariffList = document.getElementById("tariffList");
const selectedTariffHint = document.getElementById("selectedTariffHint");
const subscriptionBtn = document.getElementById("subscriptionBtn");
const changeServerBtn = document.getElementById("changeServerBtn");
const autoServerBtn = document.getElementById("autoServerBtn");
const serverValue = document.getElementById("serverValue");
const serverList = document.getElementById("serverList");
const paidServerList = document.getElementById("paidServerList");
const timeWarning = document.getElementById("timeWarning");
const onboarding = document.getElementById("onboarding");
const onboardingBtn = document.getElementById("onboardingBtn");

const INSTALL_AMNEZIA_URL = "https://amnezia.org/ru/downloads";
const REWARD_AD_URL = "";
const REWARD_WATCH_SECONDS = 20;
const FREE_ACCESS_DURATION_MS = 2 * 60 * 60 * 1000;
const FREE_ACCESS_STORAGE_KEY = "skull_vpn_free_access_until_v1";
const REWARD_READY_STORAGE_KEY = "skull_vpn_reward_ready_at_v1";
const ONBOARDING_KEY = "skull_vpn_onboarding_seen_v2";

const serverConfigs = [
  {
    name: "Нидерланды",
    emoji: "🌍",
    configUrl: "vless://replace-with-real-netherlands-config",
    pingMs: 28,
    status: "online",
    statusText: "Онлайн",
    access: "free",
  },
  {
    name: "Финляндия",
    emoji: "🌍",
    configUrl: "vmess://replace-with-real-finland-config",
    pingMs: 34,
    status: "busy",
    statusText: "Средняя нагрузка",
    access: "free",
  },
  {
    name: "Германия",
    emoji: "🌍",
    configUrl: "ss://replace-with-real-germany-config",
    pingMs: 49,
    status: "online",
    statusText: "Онлайн",
    access: "paid",
  },
  {
    name: "Турция",
    emoji: "🌍",
    configUrl: "vless://replace-with-real-turkey-config",
    pingMs: 74,
    status: "offline",
    statusText: "Техработы",
    access: "paid",
  },
];

const state = {
  mode: "disconnected",
  serverIndex: 0,
  baselineIp: null,
  baselineCountry: null,
  accessHours: 0,
  connectedCountry: null,
  checkErrorHint: "",
  tariffIndex: 0,
  hasSubscription: false,
  freeAccessUntil: 0,
  rewardReadyAt: 0,
  rewardClaimSent: false,
};

const tariffPlans = [
  {
    name: "Базовый",
    priceRub: 50,
    duration: "1 месяц",
    keys: "1 ключ на 1 устройство",
    note: "Для личного использования",
  },
  {
    name: "Стандарт",
    priceRub: 129,
    duration: "1 месяц",
    keys: "3 ключа на 3 устройства",
    note: "Телефон, планшет и ноутбук",
  },
  {
    name: "Семейный",
    priceRub: 299,
    duration: "3 месяца",
    keys: "5 ключей на 5 устройств",
    note: "Оптимально для семьи",
  },
  {
    name: "Премиум",
    priceRub: 999,
    duration: "12 месяцев",
    keys: "10 ключей на 10 устройств",
    note: "Максимальная выгода",
  },
];

function currentServer() {
  return serverConfigs[state.serverIndex];
}


function canAccessServer(server) {
  if (server.access === "free") {
    return hasFreeAccess();
  }
  return hasPaidAccess();
}

function updateServerView() {
  const active = currentServer();
  serverValue.textContent = `${active.emoji} ${active.name}`;
}

function hasPaidAccess() {
  return state.hasSubscription;
}


function hasFreeAccess() {
  return state.freeAccessUntil > Date.now();
}


function formatDurationShort(totalMs) {
  const safeMs = Math.max(0, Math.floor(totalMs));
  const totalSeconds = Math.floor(safeMs / 1000);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);

  if (hours > 0) {
    if (minutes > 0) {
      return `${hours} ч ${minutes} мин`;
    }
    return `${hours} ч`;
  }

  if (minutes > 0) {
    return `${minutes} мин`;
  }

  return "меньше минуты";
}

function statusClassByType(type) {
  if (type === "online") {
    return "meta-online";
  }
  if (type === "busy") {
    return "meta-busy";
  }
  return "meta-offline";
}

function renderServerList() {
  serverList.innerHTML = "";
  paidServerList.innerHTML = "";

  const freeServers = serverConfigs.filter((server) => server.access === "free");
  const paidServers = serverConfigs.filter((server) => server.access === "paid");

  const renderServerCard = (server, index, container, locked) => {
    const item = document.createElement("button");
    item.type = "button";
    item.className = "server-item";
    if (index === state.serverIndex && (!locked || canAccessServer(server))) {
      item.classList.add("active");
    }
    if (locked) {
      item.classList.add("locked");
    }

    item.innerHTML = `
      <div class="server-row">
        <span class="server-name">${server.emoji} ${server.name}</span>
        ${locked ? `<span class="meta-lock">${server.access === "free" ? "🔒 После рекламы" : "🔒 Нужна подписка"}</span>` : ""}
      </div>
      <div class="server-meta">
        <span class="meta-badge ${statusClassByType(server.status)}">${server.statusText}</span>
        <span>Пинг: ${server.pingMs} ms</span>
      </div>
    `;

    item.addEventListener("click", () => {
      if (locked && !canAccessServer(server)) {
        if (server.access === "free") {
          showToast("Сначала посмотрите рекламу и получите ключ на 2 часа");
          watchAdBtn.click();
        } else {
          showToast("Для этого сервера нужна подписка");
          subscriptionBtn.click();
        }
        return;
      }

      if (server.status === "offline") {
        showToast("Этот сервер временно недоступен");
        return;
      }

      state.serverIndex = serverConfigs.indexOf(server);
      updateServerView();
      renderServerList();
      showToast(`Выбран сервер: ${server.name}`);
    });

    container.appendChild(item);
  };

  freeServers.forEach((server) => {
    renderServerCard(server, serverConfigs.indexOf(server), serverList, !hasFreeAccess());
  });

  paidServers.forEach((server) => {
    renderServerCard(server, serverConfigs.indexOf(server), paidServerList, !hasPaidAccess());
  });
}

function setChip(statusClass, text) {
  statusChip.classList.remove("status-red", "status-yellow", "status-green");
  statusChip.classList.add(statusClass);
  statusChip.textContent = text;
}

function renderByMode() {
  connectBtn.classList.add("hidden");
  connectHint.classList.add("hidden");
  openAgainBtn.classList.add("hidden");
  checkBtn.classList.add("hidden");
  disconnectBtn.classList.add("hidden");
  installBtn.classList.add("hidden");

  if (state.mode === "disconnected") {
    statusTitle.textContent = "Защита не активна";
    statusSubtitle.textContent = "Подключитесь к VPN через Amnezia";
    stateHint.textContent = "Нажмите кнопку ниже, чтобы открыть Amnezia.";
    setChip("status-red", "🔴 VPN не обнаружен");
    connectBtn.classList.remove("hidden");
    connectHint.classList.remove("hidden");
    return;
  }

  if (state.mode === "waiting") {
    statusTitle.textContent = "Ожидаем подключение";
    statusSubtitle.textContent = "Подтвердите импорт конфигурации в Amnezia";
    stateHint.textContent = "После подключения нажмите «Проверить подключение».";
    setChip("status-yellow", "⏳ Ожидаем подключение...");
    openAgainBtn.classList.remove("hidden");
    checkBtn.classList.remove("hidden");
    return;
  }

  if (state.mode === "protected") {
    statusTitle.textContent = "Вы защищены";
    const location = state.connectedCountry || currentServer().name;
    statusSubtitle.textContent = `Соединение активно через ${location}`;
    stateHint.textContent = "Трафик идет через VPN-профиль Amnezia.";
    setChip("status-green", "🟢 Вы защищены");
    disconnectBtn.classList.remove("hidden");
    return;
  }

  if (state.mode === "missing-app") {
    statusTitle.textContent = "Приложение Amnezia не найдено";
    statusSubtitle.textContent = "Установите Amnezia и повторите подключение";
    stateHint.textContent = "После установки вернитесь и нажмите «Подключиться».";
    setChip("status-red", "🔴 Amnezia не обнаружена");
    installBtn.classList.remove("hidden");
    connectBtn.classList.remove("hidden");
    connectHint.classList.remove("hidden");
    return;
  }

  statusTitle.textContent = "VPN не обнаружен";
  statusSubtitle.textContent = "Завершите подключение в Amnezia";
  stateHint.textContent = state.checkErrorHint || "Откройте Amnezia повторно и проверьте подключение.";
  setChip("status-red", "🔴 VPN не обнаружен");
  openAgainBtn.classList.remove("hidden");
  checkBtn.classList.remove("hidden");
}

function syncSubscription() {
  if (state.accessHours > 0) {
    timeLeftValue.textContent = `⏳ Подписка: ${state.accessHours} часа`;
  } else {
    timeLeftValue.textContent = "⏳ Подписка не активна";
  }
  state.hasSubscription = state.accessHours > 0;
  if (state.accessHours > 0 && state.accessHours < 12) {
    timeWarning.classList.remove("hidden");
  } else {
    timeWarning.classList.add("hidden");
  }
}


function loadRewardState() {
  try {
    const storedUntil = Number(localStorage.getItem(FREE_ACCESS_STORAGE_KEY) || "0");
    const storedReadyAt = Number(localStorage.getItem(REWARD_READY_STORAGE_KEY) || "0");
    state.freeAccessUntil = Number.isFinite(storedUntil) ? storedUntil : 0;
    state.rewardReadyAt = Number.isFinite(storedReadyAt) ? storedReadyAt : 0;
  } catch (_error) {
    state.freeAccessUntil = 0;
    state.rewardReadyAt = 0;
  }
}


function saveRewardState() {
  try {
    localStorage.setItem(FREE_ACCESS_STORAGE_KEY, String(state.freeAccessUntil));
    localStorage.setItem(REWARD_READY_STORAGE_KEY, String(state.rewardReadyAt));
  } catch (_error) {
    // ignored
  }
}


function syncFreeAccessPanel() {
  const now = Date.now();
  const accessRemaining = state.freeAccessUntil - now;
  const rewardRemaining = state.rewardReadyAt - now;

  if (accessRemaining > 0) {
    freeAccessValue.textContent = `🔑 ${formatDurationShort(accessRemaining)}`;
    rewardStatus.textContent = "Ключ активен. Выберите бесплатный сервер и подключайтесь.";
    rewardTimer.textContent = `Доступ действует ещё ${formatDurationShort(accessRemaining)}.`;
    state.rewardClaimSent = true;
  } else {
    freeAccessValue.textContent = "🔒 Не активирован";
    rewardStatus.textContent = "Посмотрите рекламу в Mini App и получите ключ на 2 часа.";
    if (rewardRemaining <= 0) {
      state.rewardClaimSent = false;
    }
    if (rewardRemaining > 0) {
      rewardTimer.textContent = `Реклама просмотрена. Через ${formatDurationShort(rewardRemaining)} можно получить ключ.`;
    } else if (state.rewardClaimSent) {
      rewardTimer.textContent = "Ключ уже отправлен в чат Telegram.";
    } else {
      rewardTimer.textContent = "После просмотра рекламы нажмите кнопку получения ключа.";
    }
  }

  claimAccessBtn.disabled = !(rewardRemaining <= 0 && !state.rewardClaimSent);
}


function openRewardAd() {
  state.rewardClaimSent = false;
  state.rewardReadyAt = Date.now() + REWARD_WATCH_SECONDS * 1000;
  saveRewardState();
  syncFreeAccessPanel();

  if (REWARD_AD_URL) {
    window.open(REWARD_AD_URL, "_blank", "noopener,noreferrer");
  }

  showToast("Реклама открыта. После просмотра получите ключ на 2 часа.");
}


function claimFreeAccess() {
  const now = Date.now();
  if (state.rewardReadyAt > now) {
    showToast("Сначала досмотрите рекламу");
    return;
  }

  const payload = {
    action: "claim_free_access",
    hours: 2,
    source: "mini_app_ad",
  };

  state.rewardClaimSent = true;
  state.freeAccessUntil = Date.now() + FREE_ACCESS_DURATION_MS;
  saveRewardState();
  syncFreeAccessPanel();

  if (tg?.sendData) {
    tg.sendData(JSON.stringify(payload));
    showToast("Ключ отправлен в чат с ботом");
    return;
  }

  showToast("Mini App открыт не в Telegram — отправка ключа недоступна");
}

function currentTariff() {
  return tariffPlans[state.tariffIndex];
}

function renderTariffList() {
  tariffList.innerHTML = "";

  tariffPlans.forEach((plan, index) => {
    const item = document.createElement("button");
    item.type = "button";
    item.className = "tariff-item";
    if (index === state.tariffIndex) {
      item.classList.add("active");
    }

    item.innerHTML = `
      <div class="tariff-top">
        <span class="tariff-name">${plan.name}</span>
        <span class="tariff-price">${plan.priceRub} ₽</span>
      </div>
      <p class="tariff-meta">${plan.keys} • ${plan.duration}</p>
      <p class="tariff-note">${plan.note}</p>
    `;

    item.addEventListener("click", () => {
      state.tariffIndex = index;
      renderTariffList();
      const selected = currentTariff();
      selectedTariffHint.textContent = `Выбран тариф: ${selected.name} (${selected.priceRub} ₽)`;
    });

    tariffList.appendChild(item);
  });

  const selected = currentTariff();
  selectedTariffHint.textContent = `Выбран тариф: ${selected.name} (${selected.priceRub} ₽)`;
}

async function getPublicIpInfo() {
  const ipResp = await fetch("https://api.ipify.org?format=json", {
    cache: "no-store",
  });
  if (!ipResp.ok) {
    throw new Error("ipify request failed");
  }

  const ipData = await ipResp.json();
  const ip = ipData.ip || null;
  if (!ip) {
    throw new Error("IP not found");
  }

  const geoResp = await fetch(`https://ipapi.co/${ip}/json/`, {
    cache: "no-store",
  });
  if (!geoResp.ok) {
    throw new Error("ipapi request failed");
  }

  const geo = await geoResp.json();
  return {
    ip,
    country: geo.country_name || null,
  };
}

function showToast(text) {
  if (tg?.showPopup) {
    tg.showPopup({ title: "Skull VPN", message: text, buttons: [{ type: "ok" }] });
    return;
  }
  window.alert(text);
}

function openConfigInAmnezia() {
  const active = currentServer();
  if (!canAccessServer(active)) {
    if (active.access === "free") {
      showToast("Сначала получите бесплатный ключ на 2 часа");
      watchAdBtn.click();
    } else {
      showToast("Для этого сервера нужна подписка");
    }
    return;
  }

  if (!active.configUrl.includes("://replace-with-real")) {
    state.mode = "waiting";
    renderByMode();
    window.location.href = active.configUrl;
    return;
  }

  showToast("Добавьте реальную ссылку vless://, vmess:// или ss:// в app.js");
}

function tryOpenAmnezia() {
  let appOpened = false;
  const visibilityListener = () => {
    if (document.visibilityState === "hidden") {
      appOpened = true;
      document.removeEventListener("visibilitychange", visibilityListener);
    }
  };

  document.addEventListener("visibilitychange", visibilityListener);
  openConfigInAmnezia();

  window.setTimeout(() => {
    document.removeEventListener("visibilitychange", visibilityListener);
    if (!appOpened && state.mode === "waiting") {
      state.mode = "missing-app";
      renderByMode();
    }
  }, 1400);
}

async function verifyConnection() {
  state.mode = "waiting";
  state.checkErrorHint = "";
  renderByMode();

  try {
    const current = await getPublicIpInfo();
    const ipChanged = Boolean(state.baselineIp && current.ip !== state.baselineIp);
    const countryChanged = Boolean(
      state.baselineCountry && current.country && current.country !== state.baselineCountry
    );

    if (ipChanged || countryChanged) {
      state.mode = "protected";
      state.connectedCountry = current.country;
    } else {
      state.mode = "not-detected";
    }
  } catch (_error) {
    state.mode = "not-detected";
    state.checkErrorHint = "Не удалось проверить IP. Убедитесь, что интернет доступен.";
  }

  renderByMode();
}

function bootstrapFromTelegram() {
  if (!tg) {
    userLine.textContent = "Открыто вне Telegram: демо-режим интерфейса.";
    refLinkInput.value = "https://t.me/skull_vpn_bot?start=ref_demo";
    return;
  }

  tg.ready();
  tg.expand();

  const user = tg.initDataUnsafe?.user;
  if (user?.username) {
    userLine.textContent = `Профиль: @${user.username}`;
    refLinkInput.value = `https://t.me/skull_vpn_bot?start=ref_${user.id}`;
  } else if (user?.id) {
    userLine.textContent = `Пользователь Telegram ID: ${user.id}`;
    refLinkInput.value = `https://t.me/skull_vpn_bot?start=ref_${user.id}`;
  } else {
    userLine.textContent = "Профиль Telegram не найден, используем демо-данные.";
    refLinkInput.value = "https://t.me/skull_vpn_bot?start=ref_demo";
  }
}

connectBtn.addEventListener("click", tryOpenAmnezia);
openAgainBtn.addEventListener("click", tryOpenAmnezia);
checkBtn.addEventListener("click", verifyConnection);

disconnectBtn.addEventListener("click", () => {
  showToast("Откройте Amnezia и отключите профиль вручную");
  state.mode = "disconnected";
  state.connectedCountry = null;
  renderByMode();
});

installBtn.addEventListener("click", () => {
  window.open(INSTALL_AMNEZIA_URL, "_blank", "noopener,noreferrer");
});

copyRefBtn.addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(refLinkInput.value);
    showToast("Ссылка скопирована");
  } catch (_error) {
    showToast("Не удалось скопировать ссылку");
  }
});

subscriptionBtn.addEventListener("click", () => {
  const selected = currentTariff();
  showToast(`Оплата: ${selected.name} • ${selected.priceRub} ₽ • ${selected.duration}`);
});

changeServerBtn.addEventListener("click", () => {
  let nextIndex = state.serverIndex;
  for (let i = 0; i < serverConfigs.length; i += 1) {
    nextIndex = (nextIndex + 1) % serverConfigs.length;
    if (serverConfigs[nextIndex].status !== "offline" && canAccessServer(serverConfigs[nextIndex])) {
      break;
    }
  }

  state.serverIndex = nextIndex;
  updateServerView();
  renderServerList();
  showToast(`Выбран сервер: ${currentServer().name}`);
});

autoServerBtn.addEventListener("click", () => {
  let bestIndex = state.serverIndex;
  let bestPing = Number.POSITIVE_INFINITY;

  serverConfigs.forEach((server, index) => {
    if (!canAccessServer(server)) {
      return;
    }
    if (server.status === "offline") {
      return;
    }
    if (server.pingMs < bestPing) {
      bestPing = server.pingMs;
      bestIndex = index;
    }
  });

  if (bestPing === Number.POSITIVE_INFINITY) {
    showToast("Сначала получите бесплатный ключ на 2 часа");
    watchAdBtn.click();
    return;
  }

  state.serverIndex = bestIndex;
  updateServerView();
  renderServerList();
  showToast(`Выбран лучший сервер: ${currentServer().name}`);
});

onboardingBtn.addEventListener("click", () => {
  onboarding.classList.add("hidden");
  localStorage.setItem(ONBOARDING_KEY, "1");
});

onboardingHelpBtn.addEventListener("click", () => {
  onboarding.classList.remove("hidden");
});


watchAdBtn.addEventListener("click", openRewardAd);
claimAccessBtn.addEventListener("click", claimFreeAccess);

async function initializeBaselineIp() {
  try {
    const baseline = await getPublicIpInfo();
    state.baselineIp = baseline.ip;
    state.baselineCountry = baseline.country;
  } catch (_error) {
    state.baselineIp = null;
    state.baselineCountry = null;
  }
}

function showOnboardingIfNeeded() {
  try {
    if (localStorage.getItem(ONBOARDING_KEY) === "1") {
      onboarding.classList.add("hidden");
      return;
    }
  } catch (_error) {
    // If storage is unavailable in WebView, show onboarding each launch.
  }
  onboarding.classList.remove("hidden");
}

bootstrapFromTelegram();
loadRewardState();
updateServerView();
renderServerList();
syncSubscription();
syncFreeAccessPanel();
renderTariffList();
renderByMode();
showOnboardingIfNeeded();
initializeBaselineIp();
window.setInterval(syncFreeAccessPanel, 1000);
