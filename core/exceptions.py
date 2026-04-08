from fastapi import Request, status
from fastapi.responses import RedirectResponse, JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from core.templates import templates
import logging

logger = logging.getLogger("uvicorn.error")

# ─────────────────────────
# 1. API 요청 여부 판별 함수
# ─────────────────────────
def is_api_request(request: Request) -> bool:
    """
    요청 헤더를 분석하여 API 호출(JSON)인지 브라우저 페이지 요청인지 확인합니다.
    """
    return (
        request.headers.get("X-Requested-With") == "XMLHttpRequest" or
        "application/json" in request.headers.get("accept", "")
    )
# ────────────────────────
# 2. 전역 예외 처리기 설치
# ────────────────────────
def install_errors(app):
    
    # ───────────────────────────────────────
    # 2-1. HTTP 관련 예외 처리 (401, 404 등)
    # ───────────────────────────────────────
    @app.exception_handler(StarletteHTTPException)
    async def global_http_exception_handler(request: Request, exc: StarletteHTTPException):
        
        # [Case] 401 Unauthorized: 인증 실패 시
        if exc.status_code == status.HTTP_401_UNAUTHORIZED:

            # HTML 페이지 요청인 경우 로그인 페이지로 리다이렉트
            if "text/html" in request.headers.get("accept", ""):
                response = RedirectResponse(url="/login")
                response.delete_cookie("access_token", path="/")
                return response
        
            # API 요청인 경우 JSON 에러 메시지 반환
            return JSONResponse(
                status_code=401,
                content={"detail": exc.detail}
            )
        
        # [Case] 404 Not Found: 페이지를 찾을 수 없을 시
        if exc.status_code == status.HTTP_404_NOT_FOUND:
            response = RedirectResponse(url="/")
            response.delete_cookie("access_token", path="/")
            return response
        
        # 그 외 기타 HTTP 예외 처리
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail}
        )
    
    # ────────────────────────────────────
    # 2-2. 서버 내부 시스템 예외 처리 (500)
    # ────────────────────────────────────
    @app.exception_handler(Exception)
    async def universal_exception_handler(request: Request, exc: Exception):
        logger.error(f"Internal Server Error: {exc}", exc_info=True)

        # [API 요청 시] JSON 형태로 500 에러 반환
        if is_api_request(request):
            return JSONResponse(
                status_code=500,
                content={"detail": "서버 내부 오류가 발생했습니다. 잠시 후 다시 시도해주세요."}
            )

        # [일반 요청 시] 에러 전용 HTML 템플릿 렌더링
        return templates.TemplateResponse(
            "error.html",
            {"request" : request, "status_code" : 500, "detail": "시스템 오류가 발생했습니다." },
            status_code=500
        )