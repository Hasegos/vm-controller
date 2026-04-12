import asyncio
from celery import Celery
from db.session import SessionLocal
from crud import user_crud, vm_crud
from services.vm_service import create_new_vm_task, control_vm_power, delete_vm_task
from models.user_model import User
from core.config import settings

# ───────────────────────────────────────────
# 1. Celery 앱 초기화 (Redis Broker/Backend)
# ───────────────────────────────────────────
celery_app = Celery(
    "worker",
    broker="redis://localhost:6379/0",
    backend="redis://localhost:6379/0"
)

# ──────────────────────────
# 2. 비동기 VM 생성 태스크
# ──────────────────────────
@celery_app.task(name="create_vm_task_async")
def create_vm_task_async(user_id: str, os_type: str):
    """
    백그라운드에서 신규 가상머신을 생성합니다.
    Celery 내부에서도 VM 개수 제한을 재확인합니다. (Race Condition 대비)
    FastAPI에서 1차 체크 후 Celery 진입 사이에 동시 요청이 통과한 경우를 차단.
    """
    db = SessionLocal()
    try:
        # ─── 1. 사용자 정보 조회 ───
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return {"status": "error", "message": "User not found"}
        
        # ─── VM 개수 2차 제한 (Race Condition 대비) ───
        vm_count = vm_crud.count_vms_by_owner(db, owner_id=user_id)
        if vm_count >= settings.MAX_VM_PER_USER:
            print(f"[P1-1] VM 개수 초과 차단: user_id={user_id}, count={vm_count}")
            return {
                "status":  "error",
                "message": f"VM은 최대 {settings.MAX_VM_PER_USER}개까지 생성할 수 있습니다."
            }

        # ─── 2. VM 서비스의 비동기 로직 실행 ───
        result = asyncio.run(create_new_vm_task(db, user, os_type))
        return result
    
    except Exception as e:
        return {"status": "error", "detail": str(e)}
    
    finally:
        db.close()

# ─────────────────────────────
# 3. 비동기 VM 전원 제어 태스크
# ─────────────────────────────
@celery_app.task(name="control_vm_task_async")
def control_vm_task_async(vm_id: int, action: str, owner_id: int):
    """
    백그라운드에서 VM의 전원(Start/Stop/Reset)을 제어합니다.
    owner_id를 받아 Celery 내부에서 소유권을 재검증합니다.
    """
    db = SessionLocal()

    try:
        # ─── 1. 전원 제어 비동기 함수 실행 ───
        result = asyncio.run(control_vm_power(db, vm_id, action, owner_id))
        return result
    
    except Exception as e:
        return {"status": "error", "detail": str(e)}
    
    finally:
        db.close()

# ──────────────────────────
# 4. 비동기 VM 삭제 태스크
# ──────────────────────────
@celery_app.task(name="delete_vm_task_async")
def delete_vm_task_async(vm_id: int, owner_id: int):
    """
    백그라운드에서 VM을 완전히 삭제합니다.
    (강제 종료 → VMX 폴더 제거 → DB 레코드 삭제 → IP 회수)
    owner_id를 받아 Celery 내부에서 소유권을 재검증합니다.
    """
    db = SessionLocal()
    try:
        result = asyncio.run(delete_vm_task(db, vm_id, owner_id))
        return result
    
    except Exception as e:
        return {"status": "error", "detail": str(e)}
    
    finally:
        db.close()