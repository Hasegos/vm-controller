from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship
from db.base_class import Base

class User(Base):
    """
    데이터베이스의 'users' 테이블과 매핑되는 사용자 모델입니다.
    """

    # ───────────────────
    # 1. 테이블 설정
    # ───────────────────
    __tablename__ = "users"

    # ───────────────────
    # 2. 컬럼 정의
    # ───────────────────
    # 고유 식별자 (기본키)
    id = Column(Integer , primary_key=True, index=True)

    # 사용자 아이디 (고유값, 인덱스 생성, 필수값)
    username = Column(String, unique=True, index=True, nullable=False)

    # 암호화된 비밀번호
    hashed_password = Column(String, nullable=False)

    # ───────────────────────────
    # 3. 관계 설정 (Relationship)
    # ───────────────────────────
    # 사용자가 소유한 가상머신(VM) 목록과의 1:N 관계 정의
    # back_populates: VM 모델의 'owner' 속성과 서로 참조합니다.
    vms = relationship("VM", back_populates="owner")