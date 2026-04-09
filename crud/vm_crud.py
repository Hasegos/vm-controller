from sqlalchemy.orm import Session
from models.vm_model import VM

# ─────────────────────────────────────────────────────────────
# 1. 신규 VM 데이터베이스 레코드 생성
# ─────────────────────────────────────────────────────────────
def create_vm(db: Session, owner_id: int, ip: str, os: str, status: str = "creating"):
    """
    새로운 가상머신 정보를 DB에 기록합니다.
    - vm_name: OS 종류와 IP 마지막 자리를 조합하여 자동 생성
    """

    # ─── 1. VM 모델 객체 매핑 ───
    db_vm = VM(
        owner_id=owner_id,
        ip_address=ip,   # 모델 컬럼명: ip_address
        os_type=os,      # 모델 컬럼명: os_type
        status=status,
        vm_name=f"{os}-{ip.split('.')[-1]}"
    )

    # ─── 2. DB 반영 및 세션 갱신 ───
    db.add(db_vm)
    db.commit()
    db.refresh(db_vm)
    return db_vm

# ─────────────────────
# 2. VM 상태 업데이트
# ─────────────────────
def update_vm_status(db: Session, vm_id: int, status: str):
    """
    특정 VM의 현재 상태(running, stopping, failed 등)를 변경합니다.
    """

    # ─── 1. 대상 VM 조회 ───
    db_vm = db.query(VM).filter(VM.id == vm_id).first()

    # ─── 2. 상태 변경 및 커밋 ───
    if db_vm:
        db_vm.status = status
        db.commit()
        db.refresh(db_vm)
        
    return db_vm