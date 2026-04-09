import asyncio
from celery import Celery
from db.session import SessionLocal
from crud import user_crud
from services.vm_service import create_new_vm_task, control_vm_power

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
def create_vm_task_async(username: str, os_type: str):
    """
    백그라운드에서 신규 가상머신을 생성합니다.
    """
    db = SessionLocal()
    try:
        # ─── 1. 사용자 정보 조회 ───
        user = user_crud.get_user_by_username(db, username=username)
        if not user:
            return {"status": "error", "message": "User not found"}

        # ─── 2. VM 서비스의 비동기 로직 실행 ───
        # Celery(동기) 내부에서 async 함수를 실행하기 위해 asyncio.run 사용
        asyncio.run(create_new_vm_task(db, user, os_type))
        
        return {"status": "success", "os": os_type}
    except Exception as e:
        return {"status": "error", "detail": str(e)}
    finally:
        db.close()

# ─────────────────────────────
# 3. 비동기 VM 전원 제어 태스크
# ─────────────────────────────
@celery_app.task(name="control_vm_task_async")
def control_vm_task_async(vm_id: int, action: str):
    """
    백그라운드에서 VM의 전원(Start/Stop/Reset)을 제어합니다.
    """
    db = SessionLocal()
    try:
        # ─── 1. 전원 제어 비동기 함수 실행 ───
        result = asyncio.run(control_vm_power(db, vm_id, action))
        return result
    except Exception as e:
        return {"status": "error", "detail": str(e)}
    finally:
        db.close()