from fastapi import FastAPI , Request, status
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from db.session import engine
from db.base import Base
from api.routers import api_router
from core.config import settings
from starlette.exceptions import HTTPException as StarletteHTTPException

Base.metadata.create_all(bind=engine)

app = FastAPI(title=settings.PROJECT_NAME)

app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(api_router)

@app.get("/")
async def root():
    return {"message" : "CloudForge API Server is running"}

@app.exception_handler(StarletteHTTPException)
async def custom_http_exception_handler(request: Request, exc: StarletteHTTPException):
    # 401 Unauthorized 에러는 로그인 페이지로 리다이렉트하면서 쿠키 삭제
    if exc.status_code == status.HTTP_401_UNAUTHORIZED:
        response = RedirectResponse(url="/login")
        response.delete_cookie("access_token")
        return response
    
    # 404 Not Found 같은 다른 에러는 기본 핸들러가 처리하게 함
    # (원한다면 404 전용 페이지로 리다이렉트도 가능)
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail}
    )