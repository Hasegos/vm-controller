from sqlalchemy.orm import Session
from models.user_model import User
from core.security import verify_password, get_password_hash
from schemas import user_schema

def create_user(db: Session, user_in: user_schema.UserCreate):
    
    hashed_pw = get_password_hash(user_in.password)
    
    db_user = User(
        username=user_in.username,
        hashed_password=hashed_pw
    )
    
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

def get_user_by_username(db: Session, username: str):
    return db.query(User).filter(User.username == username).first()


def authenticate_user(db: Session, username: str, password: str):
    db_user = get_user_by_username(db, username)
    if not db_user:
        return False

    if not verify_password(password, db_user.hashed_password):
        return False
    
    return db_user