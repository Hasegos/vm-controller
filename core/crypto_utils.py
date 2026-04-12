from cryptography.fernet import Fernet
from core.config import settings

# ────────────────────────────────
# SSH 개인키 암호화/복호화 유틸리티
# ────────────────────────────────
def _get_fernet() -> Fernet:
    """
    .env의 DB_ENCRYPTION_KEY로 Fernet 인스턴스를 생성합니다.
    키가 유효하지 않으면 ValueError가 발생합니다.
    """
    return Fernet(settings.DB_ENCRYPTION_KEY.encode())

def encrypt_private_key(private_key_str: str) -> str:
    """
    PEM 형식 개인키 문자열을 암호화하여 반환합니다.
    DB에 저장할 때 사용합니다.
    """
    f = _get_fernet()
    encrypted = f.encrypt(private_key_str.encode("utf-8"))
    return encrypted.decode("utf-8")

def decrypt_private_key(encrypted_str: str) -> str:
    """
    DB에서 꺼낸 암호화된 개인키를 복호화하여 반환합니다.
    asyncssh / paramiko 접속 시 사용합니다.
    """
    f = _get_fernet()
    decrypted = f.decrypt(encrypted_str.encode("utf-8"))
    return decrypted.decode("utf-8")