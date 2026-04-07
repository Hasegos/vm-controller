from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from db.session import get_db
from schemas import user_schema
from crud import user_crud

from core.auth import get_current_user
from core.templates import templates

router = APIRouter()

@router.get("/dashboard")
async def dashboard_page(
  request: Request,
  username: str = Depends(get_current_user)
  ):
  return templates.TemplateResponse(
    request=request,
    name="dashboard.html",
    context={"request": request, "username": username}
  )