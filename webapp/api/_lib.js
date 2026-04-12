function botApiBase() {
  const base = process.env.BOT_API_URL || process.env.BOT_API_BASE_URL || "";
  if (!base) {
    throw new Error("BOT_API_URL is not configured");
  }
  return base.replace(/\/$/, "");
}

async function forwardJson(pathname, payload) {
  const response = await fetch(`${botApiBase()}${pathname}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  const text = await response.text();
  let jsonBody = null;
  try {
    jsonBody = text ? JSON.parse(text) : null;
  } catch (_error) {
    jsonBody = null;
  }

  return {
    ok: response.ok,
    status: response.status,
    body: jsonBody ?? { ok: false, raw: text },
  };
}

module.exports = {
  forwardJson,
};