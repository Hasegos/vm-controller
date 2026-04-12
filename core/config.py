from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # ───────────────────
    # 1. 가상머신(VM) 설정
    # ───────────────────
    BASE_VMX: str
    CLONE_ROOT: str

    # ─────────────────────────
    # 2. 게스트 OS 및 네트워크
    # ─────────────────────────
    GUEST_USER:str
    GUEST_PW:str

    BASE_IP:str
    GATE_IP:str
    SUBNET_MASK:str
    INTERFACE:str
    
    # ───────────────────────────
    # 3. 데이터베이스(PostgreSQL)
    # ───────────────────────────
    POSTGRESQL_USERNAME: str
    POSTGRESQL_PASSWORD: str
    POSTGRESQL_SERVER: str
    POSTGRESQL_PORT: str
    POSTGRESQL_DATABASE: str
    PROJECT_NAME:str = "CloudForge default"
    
    # ──────────────────────
    # 4. 보안 및 인증 (JWT)
    # ──────────────────────
    SECRET_KEY: str
    ALGORITHM: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int

    # ──────────────────────────
    # 5. DB 저장 개인키 암호화 키
    # ──────────────────────────
    DB_ENCRYPTION_KEY:str

    # ──────────────────────────────
    # 6. 웹 터미널 (WebSocket 보안)
    # ──────────────────────────────
    MAX_CONNECTIONS_PER_VM: int   
    RATE_LIMIT_MAX_ATTEMPTS: int    
    RATE_LIMIT_WINDOW_SEC: int   
    MAX_MESSAGE_BYTES: int

    # ─────────────────
    # 7. VM 생성 제한 
    # ─────────────────
    MAX_VM_PER_USER: int
    
    # ──────────────────────────────────────────────────────
    # 8. VM 리소스 상한 비율 
    # 게스트 OS 원본 VMX 스펙 대비 클론 VM에 허용할 비율
    # ──────────────────────────────────────────────────────
    RESOURCE_LIMIT_RATIO: float

    # ──────────────────
    # 9. 연결 수 키 TTL
    # ──────────────────
    WS_CONN_TTL: int

    # ──────────────────
    # 10. 무동작 체크
    # ──────────────────
    IDLE_TIMEOUT: int

    # ──────────────────────────
    # 11. 계산된 프로퍼티 (DB URL)
    # ──────────────────────────
    @property
    def SQLALCHEMY_DATABASE_URL(self) -> str:
        """
        입력된 정보를 바탕으로 SQLAlchemy 접속 URL을 생성합니다.
        """
        return (
            f"postgresql://{self.POSTGRESQL_USERNAME}:{self.POSTGRESQL_PASSWORD}"
            f"@{self.POSTGRESQL_SERVER}:{self.POSTGRESQL_PORT}/{self.POSTGRESQL_DATABASE}"
            f"?client_encoding=utf8"
        )
    
    # ──────────────────────────
    # 12. 환경 설정 로드 구성
    # ──────────────────────────
    model_config = SettingsConfigDict(
        env_file = ".env",
        env_file_encoding = "utf-8"
    )

# ───────────────────
# 13. 설정 객체 인스턴스화
# ───────────────────
settings = Settings()