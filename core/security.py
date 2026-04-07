import jwt
from datetime import datetime, timedelta, timezone
from typing import Optional
from passlib.context import CryptContext
from .config import settings

# --- 비밀번호 관련 함수 ---  
# 암호화 방식 설정 (BCrypt 알고리즘 사용)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_password_hash(password: str) -> str:
  return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
  return pwd_context.verify(plain_password, hashed_password)

# --- JWT 관련 함수 ---
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """JWT 액세스 토큰 생성"""
    to_encode = data.copy()
    
    # 만료 시간 설정
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        # settings에 정의한 기본값(30분) 사용
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    
    # settings의 SECRET_KEY와 ALGORITHM 사용
    encoded_jwt = jwt.encode(
        to_encode, 
        settings.SECRET_KEY, 
        algorithm=settings.ALGORITHM
    )
    return encoded_jwt

def decode_access_token(token: str):
    """JWT 토큰 복호화 및 검증"""
    try:
        # settings의 SECRET_KEY와 ALGORITHM 사용
        payload = jwt.decode(
            token, 
            settings.SECRET_KEY, 
            algorithms=[settings.ALGORITHM]
        )
        return payload
      
    except jwt.ExpiredSignatureError:
        # 토큰 만료 시
        return None
      
    except jwt.InvalidTokenError:
        # 잘못된 토큰일 시
        return None