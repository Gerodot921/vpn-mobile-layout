# Telegram Mini App Setup

## 1. Prepare HTTPS URL for webapp

Telegram opens Mini Apps only from HTTPS. Host files from `webapp/` on your domain, for example:

- `https://vpn.example.com/miniapp/index.html`

## 2. Configure bot environment

In `.env` set:

- `TELEGRAM_BOT_TOKEN=...`
- `TELEGRAM_MINI_APP_URL=https://vpn.example.com/miniapp/index.html`

## 3. Configure BotFather

1. Open BotFather and select your bot.
2. Set Menu Button URL to the same Mini App URL.
3. Save changes.

After that, Telegram will show an `Open` button in bot profile.

## 4. Start bot

Run:

```powershell
d:/ProjectM/vpn-mobile-layout/.venv/Scripts/python.exe bot.py
```

## 5. What is already implemented in this repo

- Inline button with `web_app` in start and connection flows.
- Reply-menu entry `📱 Mini App`.
- Command `/miniapp`.
- Automatic `set_chat_menu_button` on startup when `TELEGRAM_MINI_APP_URL` is valid.
- Frontend template in `webapp/index.html`, `webapp/styles.css`, `webapp/app.js`.

## 6. Local quick test (without Telegram)

You can open `webapp/index.html` in browser for UI check, but Telegram context features (`initData`, themed UI, native popup) work fully only inside Telegram WebView.
