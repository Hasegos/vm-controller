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

# ──────────────────────────────
# 3. VM 삭제 (DB 레코드 제거)
# ──────────────────────────────
def delete_vm(db: Session, vm_id: int):
    """
    DB에서 VM 레코드를 영구 삭제합니다.
    실제 VMX 파일/폴더 삭제는 vm_service에서 처리하고,
    이 함수는 DB 정리만 담당합니다.
    """

    # ─── 1. 대상 VM 조회 ───
    db_vm = db.query(VM).filter(VM.id == vm_id).first()

    # ─── 2. 존재하면 삭제 ───
    if db_vm:
        db.delete(db_vm)
        db.commit()
        return True
    
    return False

# ─────────────────────────────────────────────────────────────
# 4. IP 주소로 VM 조회 (IP 중복/회수 체크용)
# ─────────────────────────────────────────────────────────────
def get_vm_by_ip(db: Session, ip: str):
    """
    특정 IP를 가진 VM을 조회합니다.
    IP 할당 전 중복 확인에 사용합니다.
    """
    return db.query(VM).filter(VM.ip_address == ip).first()

# ──────────────────────────────────────────────────────────────
# 5. SSH 공개키 저장
# ──────────────────────────────────────────────────────────────
def update_vm_ssh_public_key(db: Session, vm_id: int, public_key: str):
    """
    VM의 SSH 공개키를 DB에 저장합니다.
    """
    db_vm = db.query(VM).filter(VM.id == vm_id).first()
    if db_vm:
        db_vm.ssh_public_key = public_key
        db.commit()
        db.refresh(db_vm)
    return db_vm

# ───────────────────
# 6. SSH 개인키 저장
# ───────────────────
def update_vm_ssh_private_key(db: Session, vm_id: int, encrypted_private_key: str):
    """
    VM의 SSH 개인키를 DB에 저장합니다.
    """
    db_vm = db.query(VM).filter(VM.id == vm_id).first()
    if db_vm:
        db_vm.ssh_private_key = encrypted_private_key
        db.commit()
        db.refresh(db_vm)
    return db_vm

# ──────────────────────────────────────────────────────────────
# 7. SSH 호스트 키 fingerprint 저장
# ──────────────────────────────────────────────────────────────
def update_vm_host_fingerprint(db: Session, vm_id: int, fingerprint: str):
    """
    VM의 SSH 호스트 키 fingerprint를 DB에 저장합니다.
    """
    db_vm = db.query(VM).filter(VM.id == vm_id).first()
    if db_vm:
        db_vm.ssh_host_fingerprint = fingerprint
        db.commit()
        db.refresh(db_vm)
    return db_vm

# ──────────────────────────────────────────────────
# 8. 사용자 소유 VM 수 조회
# ──────────────────────────────────────────────────
def count_vms_by_owner(db: Session, owner_id: int) -> int:
    """
    특정 사용자가 소유한 VM 수를 반환합니다.
    """
    return db.query(VM).filter(VM.owner_id == owner_id).count()