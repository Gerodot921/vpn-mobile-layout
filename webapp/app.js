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
const rewardPanel = document.querySelector(".reward-panel");
const adOverlay = document.getElementById("adOverlay");
const adMedia = document.getElementById("adMedia");
const adTimerText = document.getElementById("adTimerText");
const adCaption = document.getElementById("adCaption");
const refLinkInput = document.getElementById("refLink");
const referralInvites = document.getElementById("referralInvites");
const referralStats = document.getElementById("referralStats");
const userLine = document.getElementById("userLine");
const copyRefBtn = document.getElementById("copyRefBtn");
const timeLeftValue = document.getElementById("timeLeftValue");
const tariffList = document.getElementById("tariffList");
const selectedTariffHint = document.getElementById("selectedTariffHint");
const subscriptionBtn = document.getElementById("subscriptionBtn");
const paymentModal = document.getElementById("paymentModal");
const paymentModalMethods = document.getElementById("paymentModalMethods");
const paymentModalStatus = document.getElementById("paymentModalStatus");
const paymentModalTariffText = document.getElementById("paymentModalTariffText");
const paymentModalCloseBtn = document.getElementById("paymentModalCloseBtn");
const paymentModalCancelBtn = document.getElementById("paymentModalCancelBtn");
const paymentModalPayBtn = document.getElementById("paymentModalPayBtn");
const changeServerBtn = document.getElementById("changeServerBtn");
const autoServerBtn = document.getElementById("autoServerBtn");
const serverValue = document.getElementById("serverValue");
const serverList = document.getElementById("serverList");
const paidServerList = document.getElementById("paidServerList");
const timeWarning = document.getElementById("timeWarning");
const onboarding = document.getElementById("onboarding");
const onboardingStageSelect = document.getElementById("onboardingStageSelect");
const onboardingStageGuide = document.getElementById("onboardingStageGuide");
const instructionPlatformSelect = document.getElementById("instructionPlatformSelect");
const instructionAppLabel = document.getElementById("instructionAppLabel");
const instructionAppGrid = document.getElementById("instructionAppGrid");
const instructionAppVpnBtn = document.getElementById("instructionAppVpnBtn");
const instructionAppVpnIcon = document.getElementById("instructionAppVpnIcon");
const instructionAppWgBtn = document.getElementById("instructionAppWgBtn");
const instructionAppWgIcon = document.getElementById("instructionAppWgIcon");
const instructionAppLimitedNote = document.getElementById("instructionAppLimitedNote");
const instructionNextBtn = document.getElementById("instructionNextBtn");
const instructionBackBtn = document.getElementById("instructionBackBtn");
const instructionDoneBtn = document.getElementById("instructionDoneBtn");
const guideDownloadTitle = document.getElementById("guideDownloadTitle");
const guideDownloadTitleText = document.getElementById("guideDownloadTitleText");
const guideDownloadNote = document.getElementById("guideDownloadNote");
const guideDownloadBtn = document.getElementById("guideDownloadBtn");
const guideDownloadIcon = document.getElementById("guideDownloadIcon");
const guideConfigTitle = document.getElementById("guideConfigTitle");
const guideConfigNote = document.getElementById("guideConfigNote");
const guideStep2Image = document.getElementById("guideStep2Image");
const guideStep2ImageNote = document.getElementById("guideStep2ImageNote");
const guideConfiguratorValue = document.getElementById("guideConfiguratorValue");
const guideConfiguratorExample = document.getElementById("guideConfiguratorExample");
const guideCopyConfiguratorBtn = document.getElementById("guideCopyConfiguratorBtn");
const guideInsertTitle = document.getElementById("guideInsertTitle");
const guideInsertSteps = document.getElementById("guideInsertSteps");
const guideStep3Image = document.getElementById("guideStep3Image");
const guideStep3ImageNote = document.getElementById("guideStep3ImageNote");
const guideFinishTitle = document.getElementById("guideFinishTitle");
const guideStep4Image = document.getElementById("guideStep4Image");
const guideStep4ImageNote = document.getElementById("guideStep4ImageNote");
const serversPanel = document.getElementById("serversPanel");

const INSTALL_AMNEZIA_URL = "https://amnezia.org/ru/downloads";
const REWARD_AD_URL = "";
const REWARD_WATCH_SECONDS = 30;
const REWARD_READY_STORAGE_KEY = "skull_vpn_reward_ready_at_v1";
const ONBOARDING_KEY = "skull_vpn_onboarding_seen_v2";

const PAYMENT_METHODS = [
  {
    code: "telegram_stars",
    title: "⭐ Stars",
    meta: "Telegram",
  },
  {
    code: "sbp",
    title: "СБП",
    meta: "Банковский перевод",
  },
  {
    code: "crypto",
    title: "Crypto",
    meta: "USDT / TON",
  },
];

const INSTRUCTION_APPS = {
  amneziavpn: "AmneziaVPN",
  amneziawg: "AmneziaWG",
};

const INSTRUCTION_PLATFORM_LABELS = {
  windows: "Windows",
  macos: "macOS",
  ios: "iOS",
  android: "Android",
};

const INSTRUCTION_APP_HINTS = {
  amneziavpn: {
    step3Title: "3. Вставьте конфигуратор в AmneziaVPN и включите VPN.",
    step3Steps: [
      "Откройте AmneziaVPN и перейдите к добавлению подключения.",
      "Выберите импорт профиля из файла .conf.",
      "Подтвердите подключение и включите VPN.",
    ],
    step4Title: "4. Создалось новое подключение — можно подключаться.",
  },
  amneziawg: {
    step3Title: "3. Вставьте конфигуратор в AmneziaWG и включите VPN.",
    step3Steps: [
      "Откройте AmneziaWG и нажмите добавление туннеля.",
      "Импортируйте ранее скачанный файл .conf.",
      "Подтвердите подключение и включите туннель.",
    ],
    step4Title: "4. Создалось новое подключение — можно подключаться.",
  },
};

const INSTRUCTION_DOWNLOAD_URLS = {
  windows: {
    amneziavpn: "https://amnezia.org/ru/downloads",
    amneziawg: "https://amnezia.org/ru/downloads",
  },
  macos: {
    amneziavpn: "https://amnezia.org/ru/downloads",
    amneziawg: "https://amnezia.org/ru/downloads",
  },
  ios: {
    amneziavpn: "https://apps.apple.com/am/app/amneziavpn/id1600529900",
    amneziawg: "https://apps.apple.com/am/app/amneziawg/id6478942365",
  },
  android: {
    amneziavpn: "https://play.google.com/store/apps/details?id=org.amnezia.vpn",
    amneziawg: "https://play.google.com/store/apps/details?id=org.amnezia.awg",
  },
};

const INSTRUCTION_APP_ICON_DATA = {
  amneziavpn: "https://images.seeklogo.com/logo-png/48/1/amnezia-vpn-logo-png_seeklogo-488391.png",
  amneziawg: "https://play-lh.googleusercontent.com/gR0IXMSLeKkmKUAXcVCowZ95fIPPjsr2KcaTWA2Vgj6QieELc3KLMFOYGdN9iypECJY",
};

const IOS_AMNEZIA_VPN_GUIDE_IMAGES = {
  step2: "https://cdn.jsdelivr.net/gh/Gerodot921/vpn-mobile-layout@master/webapp/assets/ios-step2.png",
  step3: "https://cdn.jsdelivr.net/gh/Gerodot921/vpn-mobile-layout@master/webapp/assets/ios-step3.png",
  step4: "https://cdn.jsdelivr.net/gh/Gerodot921/vpn-mobile-layout@master/webapp/assets/ios-step4.png",
};

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
  paidRemainingText: "неизвестно",
  paidExpiresAt: null,
  paymentMethod: "telegram_stars",
  instruction: {
    platform: "windows",
    app: "amneziavpn",
    stage: "select",
  },
};

let freeServerAdInProgress = false;
let adCountdownTimer = null;

const tariffPlans = [
  {
    code: "basic",
    name: "Базовый",
    priceRub: 50,
    durationDays: 30,
    duration: "1 месяц",
    keys: "1 ключ на 1 устройство",
    note: "Для личного использования",
  },
  {
    code: "standard",
    name: "Стандарт",
    priceRub: 129,
    durationDays: 30,
    duration: "1 месяц",
    keys: "3 ключа на 3 устройства",
    note: "Телефон, планшет и ноутбук",
  },
  {
    code: "family",
    name: "Семейный",
    priceRub: 299,
    durationDays: 90,
    duration: "3 месяца",
    keys: "5 ключей на 5 устройств",
    note: "Оптимально для семьи",
  },
  {
    code: "premium",
    name: "Премиум",
    priceRub: 999,
    durationDays: 365,
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

  let date;
  try {
    date = new Date(value);
    if (Number.isNaN(date.getTime())) {
      return "-";
    }
  } catch (_error) {
    return "-";
  }

  const hours = String(date.getHours()).padStart(2, "0");
  const minutes = String(date.getMinutes()).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const year = date.getFullYear();
  return `${hours}:${minutes} ${day}.${month}.${year}`;
}


function detectInstructionPlatform() {
  const ua = String(window.navigator.userAgent || "").toLowerCase();
  const tgPlatform = String(tg?.platform || "").toLowerCase();

  if (tgPlatform.includes("ios") || ua.includes("iphone") || ua.includes("ipad") || ua.includes("ipod")) {
    return "ios";
  }
  if (tgPlatform.includes("android") || ua.includes("android")) {
    return "android";
  }
  if (ua.includes("mac os") || ua.includes("macintosh")) {
    return "macos";
  }
  return "windows";
}


function selectedInstructionAppName() {
  return INSTRUCTION_APPS[state.instruction.app] || "AmneziaVPN";
}


function selectedInstructionPlatformName() {
  return INSTRUCTION_PLATFORM_LABELS[state.instruction.platform] || "Windows";
}


function supportsWgForPlatform(platform) {
  return platform === "ios" || platform === "android";
}


function instructionDownloadUrl(platform, app) {
  const platformMap = INSTRUCTION_DOWNLOAD_URLS[platform] || INSTRUCTION_DOWNLOAD_URLS.windows;
  return platformMap[app] || INSTALL_AMNEZIA_URL;
}


function buildConfiguratorValue() {
  const rawValue = state.accessInfo?.keyValue || state.freeAccessKey || "";
  const clean = String(rawValue || "").trim();
  if (!clean) {
    return "amnezia://config/your-configurator";
  }
  if (clean.includes("://")) {
    return clean;
  }
  return `amnezia://config/${clean}`;
}


function renderInstructionSelection() {
  if (instructionPlatformSelect) {
    instructionPlatformSelect.value = state.instruction.platform;
  }

  const isLimited = !supportsWgForPlatform(state.instruction.platform);
  if (isLimited) {
    state.instruction.app = "amneziavpn";
  } else if (state.instruction.app !== "amneziawg" && state.instruction.app !== "amneziavpn") {
    state.instruction.app = "amneziavpn";
  }

  instructionAppWgBtn?.classList.toggle("hidden", isLimited);
  instructionAppGrid?.classList.toggle("single-choice", isLimited);
  instructionAppVpnBtn?.classList.toggle("single-choice", isLimited);

  instructionAppVpnBtn?.classList.toggle("active", state.instruction.app === "amneziavpn");
  instructionAppWgBtn?.classList.toggle("active", state.instruction.app === "amneziawg");

  if (instructionAppVpnIcon) {
    instructionAppVpnIcon.src = INSTRUCTION_APP_ICON_DATA.amneziavpn;
  }
  if (instructionAppWgIcon) {
    instructionAppWgIcon.src = INSTRUCTION_APP_ICON_DATA.amneziawg;
  }

  if (instructionAppLimitedNote) {
    instructionAppLimitedNote.textContent = `Выбрано: ${selectedInstructionAppName()}`;
  }
}


function renderInstructionGuide() {
  const appName = selectedInstructionAppName();
  const platformName = selectedInstructionPlatformName();
  const configValue = buildConfiguratorValue();
  const appHints = INSTRUCTION_APP_HINTS[state.instruction.app] || INSTRUCTION_APP_HINTS.amneziavpn;
  const isIosAmneziaVpn = state.instruction.platform === "ios" && state.instruction.app === "amneziavpn";

  const setGuideImage = (imgElement, noteElement, imageSrc, fallbackText) => {
    if (!imgElement || !noteElement) {
      return;
    }

    if (!imageSrc) {
      imgElement.classList.add("hidden");
      noteElement.textContent = "";
      return;
    }

    imgElement.classList.remove("hidden");
    noteElement.textContent = "";
    imgElement.onerror = () => {
      imgElement.classList.add("hidden");
      noteElement.textContent = fallbackText;
    };
    imgElement.onload = () => {
      noteElement.textContent = "";
      imgElement.classList.remove("hidden");
    };
    imgElement.src = imageSrc;
  };

  if (guideDownloadTitleText) {
    guideDownloadTitleText.textContent = `1. Скачайте приложение ${appName}`;
  }
  if (guideDownloadNote) {
    guideDownloadNote.textContent = `Для ${platformName} с официального сайта Amnezia.`;
  }
  if (guideDownloadBtn) {
    guideDownloadBtn.href = instructionDownloadUrl(state.instruction.platform, state.instruction.app);
  }
  if (guideDownloadIcon) {
    guideDownloadIcon.src = INSTRUCTION_APP_ICON_DATA[state.instruction.app] || INSTRUCTION_APP_ICON_DATA.amneziavpn;
    guideDownloadIcon.alt = appName;
  }
  if (guideConfigTitle) {
    guideConfigTitle.textContent = "2. Скачайте предоставленный конфигуратор.";
  }
  if (guideConfigNote) {
    guideConfigNote.textContent = "Получите файл в Telegram и скачайте его на устройство.";
  }
  if (guideConfiguratorValue) {
    guideConfiguratorValue.value = configValue;
  }
  if (guideConfiguratorExample) {
    guideConfiguratorExample.textContent = `Пример: ${configValue}`;
  }
  if (guideInsertTitle) {
    guideInsertTitle.textContent = appHints.step3Title;
  }
  if (guideInsertSteps) {
    const stepItems = isIosAmneziaVpn
      ? [
          "1) Откройте приложение AmneziaVPN и нажмите на иконку ➕ (плюс) или на кнопку Приступим, если у вас не было других подключений.",
          "2) Выберите вариант подключения Файл с настройками подключения.",
          "3) Выберите ранее скачанный файл .conf и нажмите Продолжить → Подключиться.",
        ]
      : appHints.step3Steps;
    guideInsertSteps.innerHTML = stepItems.map((item) => `<li>${item}</li>`).join("");
  }
  if (guideFinishTitle) {
    guideFinishTitle.textContent = appHints.step4Title || "4. Создалось новое подключение — можно подключаться.";
  }

  if (isIosAmneziaVpn) {
    setGuideImage(
      guideStep2Image,
      guideStep2ImageNote,
      IOS_AMNEZIA_VPN_GUIDE_IMAGES.step2,
      "Добавьте файл webapp/assets/ios-step2.svg"
    );
    setGuideImage(
      guideStep3Image,
      guideStep3ImageNote,
      IOS_AMNEZIA_VPN_GUIDE_IMAGES.step3,
      "Добавьте файл webapp/assets/ios-step3.svg"
    );
    setGuideImage(
      guideStep4Image,
      guideStep4ImageNote,
      IOS_AMNEZIA_VPN_GUIDE_IMAGES.step4,
      "Добавьте файл webapp/assets/ios-step4.svg"
    );
  } else {
    setGuideImage(guideStep2Image, guideStep2ImageNote, "", "");
    setGuideImage(guideStep3Image, guideStep3ImageNote, "", "");
    setGuideImage(guideStep4Image, guideStep4ImageNote, "", "");
  }
}


function setOnboardingStage(stage) {
  state.instruction.stage = stage;
  if (stage === "guide") {
    onboardingStageSelect?.classList.add("hidden");
    onboardingStageGuide?.classList.remove("hidden");
    renderInstructionGuide();
    return;
  }

  onboardingStageGuide?.classList.add("hidden");
  onboardingStageSelect?.classList.remove("hidden");
  renderInstructionSelection();
}


function closeOnboarding() {
  onboarding.classList.add("hidden");
  try {
    localStorage.setItem(ONBOARDING_KEY, "1");
  } catch (_error) {
    // ignored
  }
}


function openOnboarding() {
  state.instruction.platform = detectInstructionPlatform();
  state.instruction.app = "amneziavpn";
  onboarding.classList.remove("hidden");
  setOnboardingStage("select");
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
        ${locked ? '<span class="meta-lock">🔒 Нужна подписка</span>' : ""}
      </div>
      <div class="server-meta">
        <span class="meta-badge ${statusClassByType(server.status)}">${server.statusText}</span>
        ${server.status === "offline" ? "" : `<span>Пинг: ${server.pingMs} ms</span>`}
      </div>
    `;

    item.addEventListener("click", () => {
      if (server.access === "free" && !hasFreeAccess()) {
        void startFreeServerAdFlow(server);
        return;
      }

      if (locked && !canAccessServer(server)) {
        showToast("Для этого сервера нужна подписка");
        subscriptionBtn.click();
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
    renderServerCard(server, serverConfigs.indexOf(server), serverList, false);
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
  if (state.hasSubscription) {
    timeLeftValue.textContent = `⏳ Подписка: ${state.paidRemainingText || "активна"}`;
  } else {
    timeLeftValue.textContent = "⏳ Подписка не активна";
  }

  let hoursLeft = Number.POSITIVE_INFINITY;
  if (state.hasSubscription && state.paidExpiresAt) {
    const expiresAtTs = Date.parse(state.paidExpiresAt);
    if (Number.isFinite(expiresAtTs)) {
      hoursLeft = (expiresAtTs - Date.now()) / (1000 * 60 * 60);
    }
  }

  if (state.hasSubscription && hoursLeft < 12) {
    timeWarning.classList.remove("hidden");
  } else {
    timeWarning.classList.add("hidden");
  }
}


function selectedPaymentMethod() {
  return PAYMENT_METHODS.find((item) => item.code === state.paymentMethod) || PAYMENT_METHODS[0];
}


function renderPaymentMethodsForModal() {
  if (!paymentModalMethods) {
    return;
  }

  paymentModalMethods.innerHTML = "";
  PAYMENT_METHODS.forEach((method) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "payment-method-btn";
    if (method.code === state.paymentMethod) {
      button.classList.add("active");
    }

    button.innerHTML = `
      <span class="payment-method-title">${method.title}</span>
      <span class="payment-method-meta">${method.meta}</span>
    `;

    button.addEventListener("click", () => {
      state.paymentMethod = method.code;
      renderPaymentMethodsForModal();
      if (paymentModalStatus) {
        paymentModalStatus.textContent = `Способ оплаты: ${method.title}`;
      }
    });

    paymentModalMethods.appendChild(button);
  });

  if (paymentModalStatus) {
    paymentModalStatus.textContent = `Способ оплаты: ${selectedPaymentMethod().title}`;
  }
}


function openPaymentModal() {
  if (!paymentModal) {
    return;
  }

  const selected = currentTariff();
  if (paymentModalTariffText) {
    paymentModalTariffText.textContent = `Тариф: ${selected.name} • ${selected.priceRub} ₽ • ${selected.duration}`;
  }
  renderPaymentMethodsForModal();
  paymentModal.classList.remove("hidden");
  paymentModal.setAttribute("aria-hidden", "false");
}


function closePaymentModal() {
  if (!paymentModal) {
    return;
  }
  paymentModal.classList.add("hidden");
  paymentModal.setAttribute("aria-hidden", "true");
}


async function requestPayment(planCode, method) {
  if (!tg?.initData) {
    throw new Error("Откройте Mini App внутри Telegram");
  }

  const response = await fetch("/api/payment/create", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      initData: tg.initData,
      planCode,
      method,
    }),
  });

  const data = await response.json().catch(() => ({}));
  if (!response.ok || !data?.ok) {
    throw new Error(data?.error || "Не удалось создать платёж");
  }

  return data;
}


function openExternalLink(url) {
  if (!url) {
    return;
  }

  if (tg?.openLink) {
    tg.openLink(url);
    return;
  }

  window.open(url, "_blank", "noopener,noreferrer");
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
  if (!rewardPanel) {
    return;
  }

  const now = Date.now();
  const accessRemaining = state.freeAccessUntil - now;
  const info = state.accessInfo || {};
  const hasAnyActiveAccess =
    (typeof info.tier === "string" && info.tier !== "none") || accessRemaining > 0 || hasPaidAccess();

  rewardPanel.classList.toggle("hidden", !hasAnyActiveAccess);
  if (!hasAnyActiveAccess) {
    return;
  }

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
  rewardTimer.textContent = `Конфиг: ${configName}\nДействует до: ${expiresText}`;
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
  if (!adOverlay || !adMedia || !adCaption || !adTimerText) {
    return;
  }

  clearAdCountdownTimer();
  const imageUrl = typeof ad?.asset_url === "string" ? ad.asset_url : "";
  const totalSeconds = Number.isFinite(watchSeconds) && watchSeconds > 0 ? watchSeconds : REWARD_WATCH_SECONDS;

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
      window.setTimeout(() => {
        hideAdOverlay();
        syncFreeAccessPanel();
      }, 600);
      return;
    }
    renderAdCountdown(remaining);
  }, 1000);
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
        showToast("Успешный просмотр рекламы, вам выдан доступ к VPN на 1 час. Мы выслали вам в личные сообщения доступ к SkullVPN.");
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
  state.paidRemainingText = String(paidSubscription.remaining_text || "неизвестно");
  state.paidExpiresAt = paidSubscription.expires_at || null;

  const accessInfo = payload.access_info || {};
  state.accessInfo = {
    tier: accessInfo.tier || "none",
    keyTitle: accessInfo.key_title || "Нет доступа",
    keyValue: accessInfo.key_value || null,
    configName: accessInfo.config_name || null,
    expiresAt: accessInfo.expires_at || null,
  };

  updateReferralStats();
  syncSubscription();
  syncFreeAccessPanel();
  if (state.instruction.stage === "guide" && !onboarding.classList.contains("hidden")) {
    renderInstructionGuide();
  }
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
    });

    tariffList.appendChild(item);
  });

  const selected = currentTariff();
  selectedTariffHint.textContent = `Выбран тариф: ${selected.name} (${selected.priceRub} ₽)`;
  subscriptionBtn.textContent = "💳 Оплатить выбранный тариф";
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
      void startFreeServerAdFlow(active);
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

async function startPaymentForSelectedMethod() {
  const selected = currentTariff();
  const method = selectedPaymentMethod();

  if (subscriptionBtn) {
    subscriptionBtn.disabled = true;
  }
  if (paymentModalPayBtn) {
    paymentModalPayBtn.disabled = true;
  }
  if (paymentModalStatus) {
    paymentModalStatus.textContent = "Создаём платёж...";
  }

  try {
    const paymentData = await requestPayment(selected.code, method.code);

    if (method.code === "telegram_stars") {
      const invoiceUrl = paymentData?.invoice_url || "";
      if (!invoiceUrl) {
        throw new Error("Не удалось получить ссылку на Telegram Stars");
      }

      if (tg?.openInvoice) {
        tg.openInvoice(invoiceUrl, async (status) => {
          if (status === "paid") {
            showToast("Оплата прошла успешно, обновляем подписку...");
            await loadUserState();
            closePaymentModal();
            return;
          }
          if (status === "cancelled") {
            showToast("Оплата отменена");
            return;
          }
          if (status === "failed") {
            showToast("Платёж не прошёл");
          }
        });
      } else {
        openExternalLink(invoiceUrl);
      }

      if (paymentModalStatus) {
        paymentModalStatus.textContent = "Откройте счёт Telegram Stars и завершите оплату.";
      }
      return;
    }

    const paymentUrl = paymentData?.payment_url || "";
    if (!paymentUrl) {
      throw new Error("Платёжная ссылка не получена");
    }

    openExternalLink(paymentUrl);
    if (paymentModalStatus) {
      paymentModalStatus.textContent = `Открыта страница оплаты: ${method.title}`;
    }
    showToast(`Переход к оплате: ${method.title}`);
    closePaymentModal();
  } catch (error) {
    const message = error?.message || "Не удалось запустить оплату";
    if (paymentModalStatus) {
      paymentModalStatus.textContent = message;
    }
    showToast(message);
  } finally {
    if (subscriptionBtn) {
      subscriptionBtn.disabled = false;
    }
    if (paymentModalPayBtn) {
      paymentModalPayBtn.disabled = false;
    }
  }
}


subscriptionBtn.addEventListener("click", () => {
  openPaymentModal();
});

paymentModalPayBtn?.addEventListener("click", () => {
  void startPaymentForSelectedMethod();
});

paymentModalCloseBtn?.addEventListener("click", () => {
  closePaymentModal();
});

paymentModalCancelBtn?.addEventListener("click", () => {
  closePaymentModal();
});

paymentModal?.addEventListener("click", (event) => {
  if (event.target === paymentModal) {
    closePaymentModal();
  }
});

window.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && paymentModal && !paymentModal.classList.contains("hidden")) {
    closePaymentModal();
  }
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
  if (!hasFreeAccess() && !hasPaidAccess()) {
    let bestFreeIndex = -1;
    let bestFreePing = Number.POSITIVE_INFINITY;

    serverConfigs.forEach((server, index) => {
      if (server.access !== "free" || server.status === "offline") {
        return;
      }
      if (server.pingMs < bestFreePing) {
        bestFreePing = server.pingMs;
        bestFreeIndex = index;
      }
    });

    if (bestFreeIndex >= 0) {
      void startFreeServerAdFlow(serverConfigs[bestFreeIndex]);
      return;
    }
  }

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
    showToast("Нет доступных серверов без подписки");
    return;
  }

  state.serverIndex = bestIndex;
  updateServerView();
  renderServerList();
  showToast(`Выбран лучший сервер: ${currentServer().name}`);
});

if (instructionPlatformSelect) {
  instructionPlatformSelect.addEventListener("change", () => {
    state.instruction.platform = instructionPlatformSelect.value;
  });
}

instructionAppVpnBtn?.addEventListener("click", () => {
  state.instruction.app = "amneziavpn";
  renderInstructionSelection();
});

instructionAppWgBtn?.addEventListener("click", () => {
  if (!supportsWgForPlatform(state.instruction.platform)) {
    return;
  }
  state.instruction.app = "amneziawg";
  renderInstructionSelection();
});

instructionNextBtn?.addEventListener("click", () => {
  setOnboardingStage("guide");
});

instructionBackBtn?.addEventListener("click", () => {
  setOnboardingStage("select");
});

instructionDoneBtn?.addEventListener("click", () => {
  closeOnboarding();
});

guideCopyConfiguratorBtn?.addEventListener("click", async () => {
  if (!guideConfiguratorValue?.value) {
    return;
  }
  try {
    await navigator.clipboard.writeText(guideConfiguratorValue.value);
    showToast("Конфигуратор скопирован");
  } catch (_error) {
    showToast("Не удалось скопировать конфигуратор");
  }
});

onboardingHelpBtn.addEventListener("click", () => {
  openOnboarding();
});

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
  openOnboarding();
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
