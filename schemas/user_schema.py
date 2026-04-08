from pydantic import BaseModel, EmailStr, field_validator
import re

# ─────────────────
# 1. 로그인 스키마 
# ─────────────────
class UserLogin(BaseModel):
    """
    로그인 시 입력받는 데이터의 규격과 형식을 검증합니다.
    """
    username: str
    password: str

    # ──────────────────────
    # 1-1. 이메일 형식 검증 
    # ──────────────────────
    @field_validator('username')
    @classmethod
    def validate_username(cls, v: str) -> str:
        # 이메일 패턴 정규식
        email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_regex, v):
            raise ValueError("올바른 이메일 형식이 아닙니다.")
        return v

# ───────────────────
# 2. 회원가입 스키마 
# ───────────────────
class UserCreate(UserLogin):
    """
    UserLogin을 상속받아 동일한 이메일 검증을 유지하며, 
    비밀번호 복잡성 검사를 추가로 수행합니다.
    """
    
    # ──────────────────────────
    # 2-1. 비밀번호 복잡성 검증
    # ──────────────────────────
    @field_validator('password')
    @classmethod
    def password_complexity(cls, v: str) -> str:
        # 영문, 숫자, 특수문자 포함 및 8자 이상 조건 확인
        if not re.match(r'^(?=.*[A-Za-z])(?=.*\d)(?=.*[!@#$%^&*(),.?":{}|<>]).{8,}$', v):
            raise ValueError('비밀번호는 영문, 숫자, 특수문자를 포함하여 8자 이상이어야 합니다.')
        return v