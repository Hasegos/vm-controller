from fastapi import FastAPI , Request, status
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from db.session import engine
from db.base import Base
from api.routers import api_router
from core.config import settings
from starlette.exceptions import HTTPException as StarletteHTTPException
from core.exceptions import install_errors

# ────────────────────────────
# 1. 데이터베이스 테이블 초기화
# ────────────────────────────
# 정의된 모든 SQLAlchemy 모델을 기반으로 데이터베이스 테이블을 생성합니다.
Base.metadata.create_all(bind=engine)

# ────────────────────────────
# 2. FastAPI 앱 인스턴스 설정
# ────────────────────────────
app = FastAPI(title=settings.PROJECT_NAME)

# ──────────────────────────
# 3. 정적 파일 및 라우터 설정
# ──────────────────────────
# 3-1. 정적 파일(CSS, JS, Image 등) 경로 마운트
app.mount("/static", StaticFiles(directory="static"), name="static")

# 3-2. API 라우터 포함 (로그인, 회원가입, 대시보드 등)
app.include_router(api_router)

# ───────────────────
# 4. 예외 처리기 설치
# ───────────────────
# 커스텀 에러 핸들러(401, 404, 500 에러 처리 등)를 등록합니다.
install_errors(app)

# ──────────────────────
# 5. 기본 루트 엔드포인트
# ──────────────────────
@app.get("/")
async def root():
    """
    서버 상태를 확인하기 위한 기본 경로입니다.
    """
    return {"message" : "CloudForge API Server is running"}