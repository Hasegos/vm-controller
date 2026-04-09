from pydantic import BaseModel

# ────────────────────────────────────
# 1. VM 생성 요청 데이터 모델 (Schema)
# ────────────────────────────────────
class VMCreate(BaseModel):
    """
    프론트엔드로부터 VM 생성 요청을 받을 때 사용하는 데이터 구조입니다.
    """

    # ─── 필드 정의 ───
    os_type: str # 생성할 운영체제 종류 (예: 'Ubuntu', 'CentOS' 등)