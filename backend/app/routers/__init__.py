from app.routers.auth import router as auth_router
from app.routers.incidents import router as incidents_router

__all__ = ["auth_router", "incidents_router"]
