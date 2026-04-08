from typing import Any
from sqlalchemy.ext.declarative import as_declarative, declared_attr

# ───────────────────────────
# 1. 선언적 모델 베이스 클래스
# ───────────────────────────
@as_declarative()
class Base:
    """
    모든 데이터베이스 모델이 상속받을 기본 클래스입니다.
    """
    id: Any
    __name__: str

    # ────────────────────────────
    # 2. 테이블 이름 자동 생성 규칙
    # ────────────────────────────
    @declared_attr
    def __tablename__(cls) -> str:
        """
        클래스 이름을 소문자로 변환하여 데이터베이스 테이블 이름으로 자동 할당합니다.
        예: User 클래스 -> 'user' 테이블
        """
        return cls.__name__.lower()