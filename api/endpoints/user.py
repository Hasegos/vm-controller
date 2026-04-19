from fastapi import APIRouter, Depends, HTTPException, status, Request, Form, Response
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session
from datetime import timedelta

from db.session import get_db
from schemas import user_schema
from crud import user_crud
from core.templates import templates
from core.security import create_access_token

router = APIRouter()

# ───────────────────
# 1. 로그인 페이지
# ───────────────────
@router.get("/login")
async def login_page(request: Request):
  """
  사용자 로그인 화면을 렌더링합니다.
  """
  return templates.TemplateResponse(
    request=request,
    name="login.html",
    context={"request": request}
  )

# ───────────────────
# 2. 회원가입 페이지
# ───────────────────
@router.get("/register")
async def register_page(request: Request):
  """
    사용자 회원가입 화면을 렌더링합니다.
    """
  return templates.TemplateResponse(
    request=request,
    name="register.html",
    context={"request": request}
  )

# ─────────────────
# 3. 회원가입 처리 
# ─────────────────
@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(
  username: str = Form(...),
  password: str = Form(...),
  db: Session = Depends(get_db)
):
  # ─────────────────
  # 3-1. 유효성 검사 
  # ─────────────────
  try:
    user_in = user_schema.UserCreate(username=username, password=password)

  except ValueError as e:
    error_msg = e.errors()[0]['msg'].replace("Value error, ", "")
    raise HTTPException(
      status_code=400,
      detail=error_msg
    )

  # ──────────────────────────
  # 3-2. 중복 사용자 체크
  # ──────────────────────────  
  db_user = user_crud.get_user_by_username(db, username=user_in.username)
  if db_user:
    raise HTTPException(
      status_code=400,
      detail="이미 존재하는 사용자입니다."
    )
  
  # ──────────────────────────────
  # 3-3. 사용자 생성 및 결과 반환
  # ──────────────────────────────
  user_crud.create_user(db, user_in=user_in)  
  return {"message": "success", "redirect_url": "/login"}

# ───────────────
# 4. 로그인 처리 
# ───────────────
@router.post("/login", status_code=status.HTTP_201_CREATED)
def login(
  username: str = Form(...),
  password: str = Form(...),
  db: Session = Depends(get_db)
):
  # ──────────────────────────
  # 4-1. 입력 데이터 검증
  # ──────────────────────────
  try:
    user_schema.UserLogin(username=username, password=password)

  except ValueError as e:
    error_msg = e.errors()[0]['msg'].replace("Value error, ", "")
    raise HTTPException(
      status_code=400,
      detail=error_msg
    )

  # ──────────────────────────
  # 4-2. 사용자 인증 (ID/PW 확인)
  # ──────────────────────────
  user = user_crud.authenticate_user(db, username=username, password=password)
  if not user:
    raise HTTPException(
      status_code=status.HTTP_400_BAD_REQUEST,
      detail="아이디 또는 비밀번호가 일치하지 않습니다.",
    )
    
  # ──────────────────────────
  # 4-3. 토큰 생성 (JWT)
  # ──────────────────────────
  access_token_expires = timedelta(minutes=30)
  access_token = create_access_token(
    data={"sub": user.username},
    expires_delta=access_token_expires
  )
  

  # ────────────────────────────
  # 4-4. 응답 구성 및 쿠키 설정 
  # ────────────────────────────
  response = JSONResponse(
    content={"message": "success", "redirect_url": "/dashboard"}
  )
  response.set_cookie(
      key="access_token", 
      value=access_token, 
      httponly=True,   # XSS 공격 방지
      max_age=int(access_token_expires.total_seconds()),
      samesite="lax",
      path="/",
      secure=False     # 운영 환경(HTTPS)에서는 True 권장
  )
  
  return response

# ─────────────────
# 5. 로그아웃 처리 
# ─────────────────
@router.post("/logout")
async def logout():
  """
  인증 쿠키를 삭제하고 로그인 페이지로 리다이렉트합니다.
  """
  response = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
  response.delete_cookie("access_token", path="/")
  return response