from fastapi import Request, HTTPException, status
from .security import decode_access_token

async def get_current_user(request: Request):
    """
    쿠키에서 JWT 토큰을 추출하여 현재 로그인한 사용자를 검증합니다.
    """

    # ─────────────────────────────────
    # 1. 브라우저 쿠키에서 토큰 추출
    # ─────────────────────────────────
    # 'access_token' 쿠키를 가져오며, Bearer 접두사가 있을 경우 제거합니다.
    token = request.cookies.get("access_token")
    if token and token.startswith("Bearer "):
        token = token[7:]
    
    # ──────────────────────────
    # 2. 토큰 존재 여부 확인
    # ──────────────────────────
    # 토큰이 없으면 인증되지 않은 사용자로 간주하여 401 에러를 발생시킵니다.
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="로그인이 필요한 서비스입니다."
        )
    
    # ─────────────────────
    # 3. 토큰 해독 및 검증 
    # ─────────────────────
    payload = decode_access_token(token)
    payload = decode_access_token(token)

    # 3-1. 만료된 토큰 처리
    if payload == "expired":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="인증 세션이 만료되었습니다."
        )
    
    # 3-2. 유효하지 않은 토큰 처리
    if payload == "invalid" or not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="잘못된 접근입니다."
        )

    # ──────────────────────────
    # 4. 사용자 식별 정보 반환
    # ──────────────────────────
    # 토큰의 'sub'(subject) 필드에서 username을 추출하여 반환합니다.
    username: str = payload.get("sub")
    return username