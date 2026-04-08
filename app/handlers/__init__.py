from .callbacks import router as callbacks_router
from .commands import router as commands_router
from .menu import router as menu_router
from .start import router as start_router

__all__ = ["start_router", "menu_router", "callbacks_router", "commands_router"]
