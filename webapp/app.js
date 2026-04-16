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
const adOverlay = document.getElementById("adOverlay");
const adMedia = document.getElementById("adMedia");
const adTitle = document.getElementById("adTitle");
const adTimerText = document.getElementById("adTimerText");
const adCaption = document.getElementById("adCaption");
const adCloseBtn = document.getElementById("adCloseBtn");
const refLinkInput = document.getElementById("refLink");
const referralInvites = document.getElementById("referralInvites");
const referralStats = document.getElementById("referralStats");
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
const serversPanel = document.getElementById("serversPanel");

const INSTALL_AMNEZIA_URL = "https://amnezia.org/ru/downloads";
const REWARD_AD_URL = "";
const REWARD_WATCH_SECONDS = 30;
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
  freeAccessSource: null,
  freeAccessKey: null,
  accessInfo: {
    tier: "none",
    keyTitle: "Нет доступа",
    keyValue: null,
    configName: null,
    expiresAt: null,
  },
  rewardReadyAt: 0,
  referral: {
    referrerId: null,
    invitedCount: 0,
    bonusDays: 0,
    activated: false,
    invites: [],
  },
  adSessionToken: null,
  adWatchSeconds: REWARD_WATCH_SECONDS,
  adAssetUrl: "",
};

let freeServerAdInProgress = false;
let adCountdownTimer = null;

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


function hasVpnAccess() {
  return hasFreeAccess() || hasPaidAccess();
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


function formatDateTime(value) {
  if (!value || typeof value !== "string") {
    return "-";
  }

  const parsed = Date.parse(value);
  if (!Number.isFinite(parsed)) {
    return value;
  }

  return new Date(parsed).toLocaleString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}


function accessTitleByTier(tier) {
  if (tier === "blatnoy") {
    return "Блатной";
  }
  if (tier === "paid") {
    return "Платный";
  }
  if (tier === "free") {
    return "Бесплатный";
  }
  return "Нет доступа";
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
        ${server.status === "offline" ? "" : `<span>Пинг: ${server.pingMs} ms</span>`}
      </div>
    `;

    item.addEventListener("click", () => {
      if (locked && !canAccessServer(server)) {
        if (server.access === "free") {
          void startFreeServerAdFlow(server);
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


function scrollToServersPanel() {
  if (!serversPanel) {
    return;
  }
  serversPanel.scrollIntoView({ behavior: "smooth", block: "start" });
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
    setChip(hasVpnAccess() ? "status-green" : "status-red", hasVpnAccess() ? "VPN подключён" : "VPN не подключён");
    connectBtn.classList.remove("hidden");
    connectHint.classList.remove("hidden");
    return;
  }

  if (state.mode === "waiting") {
    statusTitle.textContent = "Ожидаем подключение";
    statusSubtitle.textContent = "Подтвердите импорт конфигурации в Amnezia";
    stateHint.textContent = "После подключения нажмите «Проверить подключение».";
    setChip(hasVpnAccess() ? "status-green" : "status-red", hasVpnAccess() ? "VPN подключён" : "VPN не подключён");
    openAgainBtn.classList.remove("hidden");
    checkBtn.classList.remove("hidden");
    return;
  }

  if (state.mode === "protected") {
    statusTitle.textContent = "Вы защищены";
    const location = state.connectedCountry || currentServer().name;
    statusSubtitle.textContent = `Соединение активно через ${location}`;
    stateHint.textContent = "Трафик идет через VPN-профиль Amnezia.";
    setChip("status-green", "VPN подключён");
    disconnectBtn.classList.remove("hidden");
    return;
  }

  if (state.mode === "missing-app") {
    statusTitle.textContent = "Приложение Amnezia не найдено";
    statusSubtitle.textContent = "Установите Amnezia и повторите подключение";
    stateHint.textContent = "После установки вернитесь и нажмите «Подключиться».";
    setChip(hasVpnAccess() ? "status-green" : "status-red", hasVpnAccess() ? "VPN подключён" : "VPN не подключён");
    installBtn.classList.remove("hidden");
    connectBtn.classList.remove("hidden");
    connectHint.classList.remove("hidden");
    return;
  }

  statusTitle.textContent = "VPN не обнаружен";
  statusSubtitle.textContent = "Завершите подключение в Amnezia";
  stateHint.textContent = state.checkErrorHint || "Откройте Amnezia повторно и проверьте подключение.";
  setChip(hasVpnAccess() ? "status-green" : "status-red", hasVpnAccess() ? "VPN подключён" : "VPN не подключён");
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


function loadRewardTimerState() {
  try {
    const storedReadyAt = Number(localStorage.getItem(REWARD_READY_STORAGE_KEY) || "0");
    state.rewardReadyAt = Number.isFinite(storedReadyAt) ? storedReadyAt : 0;
  } catch (_error) {
    state.rewardReadyAt = 0;
  }
}


function saveRewardTimerState() {
  try {
    localStorage.setItem(REWARD_READY_STORAGE_KEY, String(state.rewardReadyAt));
  } catch (_error) {
    // ignored
  }
}


function syncFreeAccessPanel() {
  const now = Date.now();
  const accessRemaining = state.freeAccessUntil - now;
  const rewardRemaining = state.rewardReadyAt - now;
  const info = state.accessInfo || {};

  const keyTitle = accessTitleByTier(info.tier);
  const keyValue = typeof info.keyValue === "string" && info.keyValue ? info.keyValue : null;
  const configName = typeof info.configName === "string" && info.configName ? info.configName : "-";
  const expiresText = formatDateTime(info.expiresAt);

  freeAccessValue.classList.remove("tier-free", "tier-paid", "tier-blatnoy");
  if (info.tier === "free") {
    freeAccessValue.classList.add("tier-free");
  } else if (info.tier === "paid") {
    freeAccessValue.classList.add("tier-paid");
  } else if (info.tier === "blatnoy") {
    freeAccessValue.classList.add("tier-blatnoy");
  }

  if (keyValue) {
    freeAccessValue.textContent = `Доступ: ${keyTitle}`;
  } else {
    freeAccessValue.textContent = `Доступ: ${keyTitle}`;
  }
  freeAccessValue.classList.remove("copyable");
  freeAccessValue.disabled = true;
  freeAccessValue.title = "";

  rewardStatus.textContent = `Ключ: ${keyValue || "-"}`;
  rewardTimer.textContent = `Конфиг: ${configName} • Действует до: ${expiresText}`;

  if (info && info.tier && info.tier !== "none") {
    watchAdBtn.classList.add("hidden");
    claimAccessBtn.classList.add("hidden");
    return;
  }

  if (accessRemaining > 0) {
    if (!info || info.tier === "none") {
      freeAccessValue.textContent = "Доступ: Бесплатный";
      rewardStatus.textContent = `Ключ: ${state.freeAccessKey || "-"}`;
      rewardTimer.textContent = `Конфиг: free-access • Действует до: ${formatDateTime(new Date(now + accessRemaining).toISOString())}`;
    }
    watchAdBtn.classList.add("hidden");
    claimAccessBtn.classList.add("hidden");
  } else if (rewardRemaining > 0) {
    if (!info || info.tier === "none") {
      freeAccessValue.textContent = "Нет активного доступа";
      rewardStatus.textContent = "Ключ: -";
      rewardTimer.textContent = `Конфиг: - • Можно получить через ${formatDurationShort(rewardRemaining)}`;
    }
    watchAdBtn.classList.add("hidden");
    claimAccessBtn.classList.remove("hidden");
    claimAccessBtn.disabled = true;
  } else if (state.rewardReadyAt > 0) {
    if (!info || info.tier === "none") {
      freeAccessValue.textContent = "Нет активного доступа";
      rewardStatus.textContent = "Ключ: -";
      rewardTimer.textContent = "Конфиг: - • Профиль можно получить сейчас";
    }
    watchAdBtn.classList.add("hidden");
    claimAccessBtn.classList.remove("hidden");
    claimAccessBtn.disabled = false;
  } else {
    if (!info || info.tier === "none") {
      freeAccessValue.textContent = "Нет активного доступа";
      rewardStatus.textContent = "Ключ: -";
      rewardTimer.textContent = "Конфиг: - • Смотрите рекламу для получения бесплатного доступа";
    }
    watchAdBtn.classList.remove("hidden");
    claimAccessBtn.classList.add("hidden");
  }
}


function clearAdCountdownTimer() {
  if (adCountdownTimer !== null) {
    window.clearInterval(adCountdownTimer);
    adCountdownTimer = null;
  }
}


function hideAdOverlay() {
  clearAdCountdownTimer();
  if (adOverlay) {
    adOverlay.classList.add("hidden");
    adOverlay.setAttribute("aria-hidden", "true");
  }
}


function renderAdCountdown(remainingSeconds) {
  if (!adTimerText) {
    return;
  }
  adTimerText.textContent = `${Math.max(0, remainingSeconds)} сек`;
}


function showAdOverlay(ad, watchSeconds) {
  if (!adOverlay || !adMedia || !adTitle || !adCaption || !adTimerText) {
    return;
  }

  clearAdCountdownTimer();
  const imageUrl = typeof ad?.asset_url === "string" ? ad.asset_url : "";
  const title = typeof ad?.title === "string" && ad.title ? ad.title : "Рекламное предложение";
  const totalSeconds = Number.isFinite(watchSeconds) && watchSeconds > 0 ? watchSeconds : REWARD_WATCH_SECONDS;

  adTitle.textContent = title;
  adCaption.textContent = `Просмотрите рекламу ${totalSeconds} секунд, чтобы открыть 1 час бесплатного VPN.`;
  adMedia.src = imageUrl;
  renderAdCountdown(totalSeconds);
  adOverlay.classList.remove("hidden");
  adOverlay.setAttribute("aria-hidden", "false");

  let remaining = totalSeconds;
  adCountdownTimer = window.setInterval(() => {
    remaining -= 1;
    if (remaining <= 0) {
      renderAdCountdown(0);
      clearAdCountdownTimer();
      adCaption.textContent = "Реклама просмотрена. Теперь можно получить доступ.";
      return;
    }
    renderAdCountdown(remaining);
  }, 1000);
}


function openRewardAd() {
  void startRewardAdFlow();
}


async function requestAdSession() {
  if (!tg?.initData) {
    throw new Error("Откройте Mini App внутри Telegram");
  }

  const response = await fetch("/api/ad/start", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ initData: tg.initData }),
  });

  const data = await response.json().catch(() => ({}));
  if (!response.ok || !data?.ok) {
    throw new Error(data?.error || "Не удалось запустить рекламу");
  }

  return data;
}


async function completeAdSession() {
  if (!tg?.initData) {
    throw new Error("Откройте Mini App внутри Telegram");
  }
  if (!state.adSessionToken) {
    throw new Error("Сессия рекламы не найдена");
  }

  const response = await fetch("/api/ad/complete", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      initData: tg.initData,
      sessionToken: state.adSessionToken,
      watchedSeconds: state.adWatchSeconds,
    }),
  });

  const data = await response.json().catch(() => ({}));
  if (!response.ok || !data?.ok) {
    throw new Error(data?.error || "Просмотр рекламы не подтвержден");
  }
}


async function startRewardAdFlow() {
  try {
    const data = await requestAdSession();
    const ad = data?.ad || {};
    const watchSeconds = Number(ad.duration_sec || REWARD_WATCH_SECONDS);

    state.adSessionToken = data?.session_token || null;
    state.adWatchSeconds = Number.isFinite(watchSeconds) && watchSeconds > 0
      ? watchSeconds
      : REWARD_WATCH_SECONDS;
    state.adAssetUrl = typeof ad.asset_url === "string" ? ad.asset_url : "";

    state.rewardReadyAt = Date.now() + state.adWatchSeconds * 1000;
    saveRewardTimerState();
    syncFreeAccessPanel();

    showAdOverlay(ad, state.adWatchSeconds);

    showToast("Реклама открыта. После просмотра получите профиль на 1 час.");
  } catch (error) {
    showToast(error?.message || "Не удалось запустить рекламу");
  }
}


async function requestFreeAccess() {
  if (!tg?.initData) {
    throw new Error("Откройте Mini App внутри Telegram");
  }

  const response = await fetch("/api/claim-free-access", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ initData: tg.initData }),
  });

  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data?.error || "Не удалось получить доступ");
  }

  return data;
}


function claimFreeAccess() {
  const now = Date.now();
  if (state.rewardReadyAt > now) {
    showToast("Сначала досмотрите рекламу");
    return;
  }
  if (!state.adSessionToken) {
    showToast("Сначала запустите рекламу");
    return;
  }

  claimAccessBtn.disabled = true;

  completeAdSession()
    .then(() => requestFreeAccess())
    .then((data) => {
      state.adSessionToken = null;
      state.adWatchSeconds = REWARD_WATCH_SECONDS;
      state.adAssetUrl = "";
      state.rewardReadyAt = 0;
      saveRewardTimerState();
      applyUserState(data);
      showToast("Бесплатный доступ активирован");
    })
    .catch((error) => {
      claimAccessBtn.disabled = false;
      showToast(error.message || "Не удалось получить доступ");
    });
}


async function startFreeServerAdFlow(server) {
  if (freeServerAdInProgress) {
    showToast("Реклама уже запущена, дождитесь окончания");
    return;
  }

  freeServerAdInProgress = true;
  try {
    const data = await requestAdSession();
    const ad = data?.ad || {};
    const watchSeconds = Number(ad.duration_sec || REWARD_WATCH_SECONDS);

    state.adSessionToken = data?.session_token || null;
    state.adWatchSeconds = Number.isFinite(watchSeconds) && watchSeconds > 0
      ? watchSeconds
      : REWARD_WATCH_SECONDS;
    state.adAssetUrl = typeof ad.asset_url === "string" ? ad.asset_url : "";
    state.rewardReadyAt = Date.now() + state.adWatchSeconds * 1000;
    saveRewardTimerState();
    syncFreeAccessPanel();

    showAdOverlay(ad, state.adWatchSeconds);

    showToast(`Реклама запущена на ${state.adWatchSeconds} секунд`);

    window.setTimeout(async () => {
      try {
        await completeAdSession();
        state.rewardReadyAt = 0;
        saveRewardTimerState();

        const accessData = await requestFreeAccess();
        state.adSessionToken = null;
        state.adWatchSeconds = REWARD_WATCH_SECONDS;
        state.adAssetUrl = "";
        applyUserState(accessData);

        state.serverIndex = serverConfigs.indexOf(server);
        updateServerView();
        renderServerList();

        hideAdOverlay();
        showToast("Успешный просмотр рекламы, вам выдан доступ к VPN на 1 час.");
      } catch (error) {
        const message = error?.message || "Не удалось выдать доступ после рекламы";
        showToast(message);
      } finally {
        freeServerAdInProgress = false;
        syncFreeAccessPanel();
      }
    }, state.adWatchSeconds * 1000);
  } catch (error) {
    freeServerAdInProgress = false;
    state.rewardReadyAt = 0;
    saveRewardTimerState();
    hideAdOverlay();
    syncFreeAccessPanel();
    showToast(error?.message || "Не удалось запустить рекламу");
  }
}


function updateReferralStats() {
  const invitedCount = state.referral?.invitedCount || 0;
  const bonusDays = state.referral?.bonusDays || 0;
  referralStats.textContent = `👥 Приглашено: ${invitedCount} • 🎁 Дней: ${bonusDays}`;

  if (!referralInvites) {
    return;
  }

  referralInvites.innerHTML = "";
  const invites = Array.isArray(state.referral?.invites) ? state.referral.invites : [];
  if (invites.length === 0) {
    return;
  }

  invites.forEach((invite) => {
    const username = typeof invite?.username === "string" && invite.username
      ? invite.username
      : "unknown";
    const activatedAt = typeof invite?.activated_at === "string" ? invite.activated_at : "";
    const parsed = activatedAt ? Date.parse(activatedAt) : Number.NaN;
    const dateText = Number.isFinite(parsed)
      ? new Date(parsed).toLocaleString("ru-RU", {
          day: "2-digit",
          month: "2-digit",
          year: "numeric",
          hour: "2-digit",
          minute: "2-digit",
        })
      : activatedAt;

    const row = document.createElement("div");
    row.className = "ref-invite-row";
    row.innerHTML = `
      <div class="ref-invite-top">
        <span class="ref-invite-user">${username.startsWith("@") ? username : `@${username}`}</span>
        <span class="ref-invite-badge">Активирован</span>
      </div>
      <div class="ref-invite-date">${dateText}</div>
    `;
    referralInvites.appendChild(row);
  });
}


function applyUserState(payload) {
  if (!payload || typeof payload !== "object") {
    return;
  }

  const referral = payload.referral || {};
  state.referral = {
    referrerId: referral.referrer_id ?? null,
    invitedCount: Number(referral.invited_count || 0),
    bonusDays: Number(referral.bonus_days || 0),
    activated: Boolean(referral.activated),
    invites: Array.isArray(referral.invites) ? referral.invites : [],
  };

  const freeAccess = payload.free_access || {};
  state.freeAccessUntil = freeAccess.expires_at ? Date.parse(freeAccess.expires_at) || 0 : 0;
  state.freeAccessSource = freeAccess.source || null;
  state.freeAccessKey = freeAccess.access_key || null;

  const paidSubscription = payload.paid_subscription || {};
  state.hasSubscription = Boolean(paidSubscription.active);

  const accessInfo = payload.access_info || {};
  state.accessInfo = {
    tier: accessInfo.tier || "none",
    keyTitle: accessInfo.key_title || "Нет доступа",
    keyValue: accessInfo.key_value || null,
    configName: accessInfo.config_name || null,
    expiresAt: accessInfo.expires_at || null,
  };

  updateReferralStats();
  syncFreeAccessPanel();
  renderServerList();
  renderByMode();
}


async function loadUserState() {
  if (!tg?.initData) {
    updateReferralStats();
    syncFreeAccessPanel();
    return;
  }

  try {
    const response = await fetch("/api/user-state", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ initData: tg.initData }),
    });

    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(data?.error || "Не удалось загрузить состояние пользователя");
    }

    applyUserState(data);
  } catch (_error) {
    updateReferralStats();
    syncFreeAccessPanel();
  }
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
      showToast("Сначала получите бесплатный WireGuard-профиль на 1 час");
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

  showToast("WireGuard-профиль еще не подключен к Mini App. Получите его в Telegram-боте.");
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

connectBtn.addEventListener("click", scrollToServersPanel);
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

freeAccessValue.addEventListener("click", async () => {
  const copyValue = state.accessInfo?.keyValue || state.freeAccessKey;
  if (!copyValue) {
    return;
  }

  try {
    await navigator.clipboard.writeText(copyValue);
    showToast("Ключ скопирован");
  } catch (_error) {
    showToast("Не удалось скопировать ключ");
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
    showToast("Сначала получите бесплатный WireGuard-профиль на 1 час");
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

if (adCloseBtn) {
  adCloseBtn.addEventListener("click", () => {
    if (state.rewardReadyAt > Date.now()) {
      showToast("Досмотрите рекламу до конца");
      return;
    }
    hideAdOverlay();
  });
}

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
loadRewardTimerState();
updateServerView();
renderServerList();
syncSubscription();
syncFreeAccessPanel();
renderTariffList();
renderByMode();
showOnboardingIfNeeded();
initializeBaselineIp();
loadUserState();
window.setInterval(syncFreeAccessPanel, 1000);
