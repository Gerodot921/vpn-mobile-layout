import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.types import MenuButtonWebApp, WebAppInfo
from dotenv import load_dotenv

from app.handlers import callbacks_router, commands_router, menu_router, start_router
from app.subscriptions import reminder_loop


def build_dispatcher() -> Dispatcher:
    dp = Dispatcher()
    dp.include_router(start_router)
    dp.include_router(commands_router)
    dp.include_router(menu_router)
    dp.include_router(callbacks_router)
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
    try:
        await dp.start_polling(bot)
    finally:
        reminder_task.cancel()
        try:
            await reminder_task
        except asyncio.CancelledError:
            pass


def run() -> None:
    asyncio.run(main())
