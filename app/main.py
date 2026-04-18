import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.types import MenuButtonWebApp, WebAppInfo
from aiohttp import web
from dotenv import load_dotenv

from app.api import create_api_app
from app.free_access import free_access_cleanup_loop, free_access_reminder_loop
from app.handlers import callbacks_router, commands_router, menu_router, start_router, webapp_router
from app.subscriptions import reminder_loop


def build_dispatcher() -> Dispatcher:
    dp = Dispatcher()
    dp.include_router(start_router)
    dp.include_router(commands_router)
    dp.include_router(menu_router)
    dp.include_router(callbacks_router)
    dp.include_router(webapp_router)
    return dp


async def main() -> None:
    load_dotenv()
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN is not set. Create .env and add your token."
        )

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    bot = Bot(token=token)

    api_app = create_api_app(bot)
    api_runner = web.AppRunner(api_app)
    await api_runner.setup()
    api_host = os.getenv("MINI_APP_API_HOST", "0.0.0.0")
    api_port = int(os.getenv("MINI_APP_API_PORT", "8081"))
    api_site = web.TCPSite(api_runner, host=api_host, port=api_port)
    await api_site.start()
    logging.info("Mini App API server started on %s:%s", api_host, api_port)

    mini_app_url = os.getenv("TELEGRAM_MINI_APP_URL", "").strip()
    if mini_app_url.startswith("https://"):
        await bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(
                text="Open VPN",
                web_app=WebAppInfo(url=mini_app_url),
            )
        )
        logging.info("Mini App menu button configured: %s", mini_app_url)
    elif mini_app_url:
        logging.warning("TELEGRAM_MINI_APP_URL ignored: URL must start with https://")

    dp = build_dispatcher()
    reminder_task = asyncio.create_task(reminder_loop(bot))
    free_access_cleanup_task = asyncio.create_task(free_access_cleanup_loop())
    free_access_reminder_task = asyncio.create_task(free_access_reminder_loop(bot))
    try:
        await dp.start_polling(bot)
    finally:
        reminder_task.cancel()
        free_access_cleanup_task.cancel()
        free_access_reminder_task.cancel()
        try:
            await reminder_task
        except asyncio.CancelledError:
            pass
        try:
            await free_access_cleanup_task
        except asyncio.CancelledError:
            pass
        try:
            await free_access_reminder_task
        except asyncio.CancelledError:
            pass
        await api_runner.cleanup()


def run() -> None:
    asyncio.run(main())
