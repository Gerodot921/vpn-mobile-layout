from .callbacks import router as callbacks_router
from .commands import router as commands_router
from .menu import router as menu_router
from .payments import router as payments_router
from .start import router as start_router
from .webapp import router as webapp_router

__all__ = [
	"start_router",
	"menu_router",
	"callbacks_router",
	"commands_router",
	"payments_router",
	"webapp_router",
]
