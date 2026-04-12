from fastapi import APIRouter
from .endpoints import user, dashboard, terminal

api_router = APIRouter()

api_router.include_router(user.router, prefix="", tags=["users"])
api_router.include_router(dashboard.router, prefix="", tags=["dashboard"])
api_router.include_router(terminal.router, prefix="", tags=["terminal"] )