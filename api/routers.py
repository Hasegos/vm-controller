from fastapi import APIRouter
from .endpoints import user, dashboard

api_router = APIRouter()

api_router.include_router(user.router, prefix="", tags=["users"])
api_router.include_router(dashboard.router, prefix="", tags=["dashboard"])