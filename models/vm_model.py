from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from db.base_class import Base

class VM(Base):
    """
    데이터베이스의 'vms' 테이블과 매핑되는 가상 머신 정보 모델입니다.
    """

    # ───────────────────
    # 1. 테이블 설정
    # ───────────────────
    __tablename__ = "vms"

    # ───────────────────
    # 2. 컬럼 정의
    # ───────────────────
    # 고유 식별자 (기본키)
    id = Column(Integer, primary_key=True, index=True)

    # 가상 머신 이름 및 OS 유형
    vm_name = Column(String,index=True)
    os_type = Column(String)

    # 할당된 IP 주소 (고유값, 초기 생성 시에는 비어있을 수 있음)
    ip_address = Column(String, unique=True, nullable= True)

    # 현재 서버 상태 (기본값: 생성 중)
    status = Column(String, default="creating")

    # ───────────────────────
    # 3. 외래키 및 관계 설정
    # ───────────────────────
    # 3-1. 외래키: 'users' 테이블의 'id' 컬럼을 참조합니다.
    owner_id = Column(Integer, ForeignKey("users.id"))

    # 3-2. 관계: 해당 VM을 소유한 사용자(User) 객체와 연결됩니다.
    # back_populates: User 모델의 'vms' 속성과 서로 참조합니다.
    owner = relationship("User", back_populates="vms")