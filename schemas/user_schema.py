from pydantic import BaseModel, EmailStr, field_validator
import re

class UserLogin(BaseModel):
    username: EmailStr
    password: str

class UserCreate(UserLogin):
    
    @field_validator('password')
    @classmethod
    def password_complexity(cls, v: str) -> str:
        if not re.match(r'^(?=.*[A-Za-z])(?=.*\d)(?=.*[!@#$%^&*(),.?":{}|<>]).{8,}$', v):
            raise ValueError('비밀번호는 영문, 숫자, 특수문자를 포함하여 8자 이상이어야 합니다.')
        return v