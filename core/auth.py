from fastapi import Request, HTTPException, status
from .security import decode_access_token

async def get_current_user(request: Request):
    # 1. 브라우저 쿠키에서 'access_token' 가져오기
    token = request.cookies.get("access_token")
    if token and token.startswith("Bearer "):
        token = token[7:]
    
    # 2. 토큰이 없으면 로그인 페이지로 튕겨내기
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="로그인이 필요한 서비스입니다."
        )
    
    # 3. 토큰 해독 및 검증
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="인증이 만료되었습니다. 다시 로그인해주세요."
        )
    
    # 4. 토큰 속의 사용자 정보(email 등) 반환
    username: str = payload.get("sub")
    return username