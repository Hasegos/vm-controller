from fastapi import APIRouter, Depends, HTTPException, status, Request, Form, Response
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from datetime import timedelta

from db.session import get_db
from schemas import user_schema
from crud import user_crud
from core.templates import templates
from core.security import create_access_token

router = APIRouter()

# 로그인 페이지
@router.get("/login")
async def login_page(request: Request):
  return templates.TemplateResponse(
    request=request,
    name="login.html",
    context={"request": request}
  )

# 회원가입 페이지
@router.get("/register")
async def register_page(request: Request):
  return templates.TemplateResponse(
    request=request,
    name="register.html",
    context={"request": request}
  )

# 회원가입 (Register)
@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(
  username: str = Form(...),
  password: str = Form(...),
  db: Session = Depends(get_db)
):
  try:
    user_in = user_schema.UserCreate(username=username, password=password)
  except ValueError as e:
    error_msg = str(e).split('\n')[-1]
    raise HTTPException(
      status_code=400,
      detail=error_msg
    )
    
  db_user = user_crud.get_user_by_username(db, username=user_in.username)
  if db_user:
    raise HTTPException(
      status_code=400,
      detail="이미 존재하는 사용자입니다."
    )
  
  user_crud.create_user(db, user_in=user_in)  
  return {"message": "success", "redirect_url": "/login"}

# 로그인 (Login)
@router.post("/login", status_code=status.HTTP_201_CREATED)
def login(
  username: str = Form(...),
  password: str = Form(...),
  db: Session = Depends(get_db)
):
  user = user_crud.authenticate_user(db, username=username, password=password)

  if not user:
    raise HTTPException(
      status_code=status.HTTP_401_UNAUTHORIZED,
      detail="아이디 또는 비밀번호가 일치하지 않습니다.",
    )
    
  access_token_expires = timedelta(minutes=30)
  access_token = create_access_token(
    data={"sub": user.username},
    expires_delta=access_token_expires
  )
  
  response = JSONResponse(
    content={"message": "success", "redirect_url": "/dashboard"}
  )
  response.set_cookie(
      key="access_token", 
      value=access_token, 
      httponly=True,
      max_age=1800,
      samesite="lax",
      path="/",
      secure=False # 개발에서는 False 배포에서는 True로 설정
  )
  
  return response

# 로그아웃 (Logout)
@router.post("/logout")
async def logout():
  response = JSONResponse(
  content={"message": "success", "redirect_url": "/login"}
  )
  response.delete_cookie("access_token")
  return response