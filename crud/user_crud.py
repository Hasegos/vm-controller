from sqlalchemy.orm import Session
from models.user_model import User
from core.security import verify_password, get_password_hash
from schemas import user_schema

# ────────────────────────────
# 1. 신규 사용자 생성 (Create)
# ────────────────────────────
def create_user(db: Session, user_in: user_schema.UserCreate):
    """
    새로운 사용자를 데이터베이스에 등록합니다.
    """
    
    # 1-1. 비밀번호 암호화
    hashed_pw = get_password_hash(user_in.password)
    
    # 1-2. DB 모델 객체 생성
    db_user = User(
        username=user_in.username,
        hashed_password=hashed_pw
    )
    
    # 1-3. DB 저장 및 동기화
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

# ─────────────────────
# 2. 사용자 조회 (Read)
# ─────────────────────
def get_user_by_username(db: Session, username: str):
    """
    사용자 이름을 기준으로 특정 사용자를 조회합니다.
    """
    return db.query(User).filter(User.username == username).first()

# ──────────────────────────────
# 3. 사용자 인증 (Authenticate)
# ──────────────────────────────
def authenticate_user(db: Session, username: str, password: str):
    """
    로그인 시 아이디와 비밀번호를 검증합니다.
    """
    # 3-1. 사용자 존재 여부 확인
    db_user = get_user_by_username(db, username)
    if not db_user:
        return False

    # 3-2. 암호화된 비밀번호 비교 검증
    if not verify_password(password, db_user.hashed_password):
        return False
    
    # 인증 성공 시 사용자 객체 반환
    return db_user