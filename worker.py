import os
import asyncio

from io import StringIO
from celery import Celery
from db.session import SessionLocal
from crud import user_crud, vm_crud
from services.vm_service import create_new_vm_task, control_vm_power, delete_vm_task

from models.vm_model import VM
from models.user_model import User
from core.config import settings
from core.crypto_utils import decrypt_private_key
from core.vm_manager import VMwareController

# ───────────────────────────────────────────
# 1. Celery 앱 초기화 (Redis Broker/Backend)
# ───────────────────────────────────────────
celery_app = Celery(
    "worker",
    broker="redis://localhost:6379/0",
    backend="redis://localhost:6379/0"
)

# ─────────────────────────────
# 2. Celery beat 스케줄 설정
# ─────────────────────────────
celery_app.conf.beat_schedule = {
    "collect-vm-resources-every-30s": {
        "task":     "collect_vm_resources",
        "schedule": 30.0,
    },

    "sync-vm-status-every-60s": {
        "task":     "sync_vm_status",
        "schedule": 60.0,
    }
}

celery_app.conf.timezone = "Asia/Seoul"

# ──────────────────────────
# 3. 비동기 VM 생성 태스크
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
            print(f"VM 개수 초과 차단: user_id={user_id}, count={vm_count}")
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
# 4. 비동기 VM 전원 제어 태스크
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
# 5. 비동기 VM 삭제 태스크
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
        
# ──────────────────────────
# 6. VM 리소스 수집 태스크
# ──────────────────────────
@celery_app.task(name="collect_vm_resources")
def collect_vm_resources():
    """
    실행 중인 모든 VM의 CPU/RAM 사용률을 30초마다 수집합니다.
    - SSH 접속 및 명령어 실행
    - 수집 실패 시 fail_count 증가, 3회 연속 실패 시 error 처리
    - CPU 90% 이상 시 is_overloaded=True
    """
    db = SessionLocal()
    try:
        # ─── 실행 중인 VM만 조회 ───
        running_vms = db.query(VM).filter(VM.status == "running").all()

        if not running_vms:
            return {"status": "success", "message": "실행 중인 VM 없음"}

        print(f"[모니터링] 리소스 수집 시작: {len(running_vms)}개 VM")

        for vm in running_vms:
            # ─── 개인키 또는 IP 없으면 스킵 ───
            if not vm.ssh_private_key or not vm.ip_address:
                continue

            # ─── vmrun 프로세스 체크 선행 (꺼진 VM SSH 시도 방지) ───
            try:
                last_octet = vm.ip_address.split(".")[-1]
                vmx_path   = os.path.join(settings.CLONE_ROOT, f"Clone_{last_octet}", f"Clone_{last_octet}.vmx")
                if not os.path.exists(vmx_path) or not VMwareController(vmx_path).is_running():
                    vm_crud.reset_vm_to_stopped(db, vm.id, "stopped")
                    continue
            except Exception:
                continue

            try:
                # ─── 개인키 복호화 ───
                private_key_str = decrypt_private_key(vm.ssh_private_key)

                # ─── vm_manager에 SSH 수집 위임 ───
                result = VMwareController.collect_resources(
                    ip=vm.ip_address,
                    guest_user=settings.GUEST_USER,
                    pkey_str=private_key_str,
                    os_type=vm.os_type
                )

                if result is not None:
                    cpu_usage, mem_usage = result
                    vm_crud.update_vm_resources(db, vm.id, cpu_usage, mem_usage)
                    print(f"[모니터링] VM {vm.id} ({vm.ip_address}) CPU: {cpu_usage}% / MEM: {mem_usage}%")
                    
                else:
                    vm_crud.increment_vm_ssh_fail(db, vm.id)

            except Exception as e:
                print(f"[모니터링] VM {vm.id} 수집 오류: {e}")
                vm_crud.increment_vm_ssh_fail(db, vm.id)

        return {"status": "success", "collected": len(running_vms)}

    except Exception as e:
        print(f"[모니터링] 전체 수집 오류: {e}")
        return {"status": "error", "detail": str(e)}
    
    finally:
        db.close()

# ──────────────────────────────────────
# 7. VM 상태 자동 동기화 태스크
# ──────────────────────────────────────
@celery_app.task(name="sync_vm_status")
def sync_vm_status():
    """
    실행 중인 모든 VM의 실제 구동 상태를 60초마다 검증하고 DB를 자동 보정합니다.
    - VMX 파일 부재 시 status='error' 처리
    - vmrun 프로세스 종료 감지 시 status='stopped', cpu/mem=None 초기화
    """
    db = SessionLocal()
    synced = []
    errors = []

    try:
        # ─── 1. running 상태 VM 전체 조회 ───
        running_vms = db.query(VM).filter(VM.status == "running").all()

        if not running_vms:
            return {"status": "success", "message": "동기화 대상 없음"}

        print(f"체크 대상: {len(running_vms)}개 VM")

        for vm in running_vms:
            # ─── 2. IP 없는 VM 스킵 (생성 중 비정상 레코드 방어) ───
            if not vm.ip_address or not vm.ssh_private_key:
                continue

            try:
                # ─── 3. IP 마지막 옥텟으로 VMX 경로 계산 ───
                last_octet   = vm.ip_address.split(".")[-1]
                vmx_path     = os.path.join(
                    settings.CLONE_ROOT,
                    f"Clone_{last_octet}",
                    f"Clone_{last_octet}.vmx"
                )

                # ─── 4. VMX 파일 부재 → error 처리 ───
                if not os.path.exists(vmx_path):
                    print(f"VM {vm.id}: VMX 없음 → error")
                    vm_crud.reset_vm_to_stopped(db, vm.id, "error")
                    synced.append({"vm_id": vm.id, "result": "error(no_vmx)"})
                    continue

                manager = VMwareController(vmx_path)
                
                # ─── 5. vmrun list로 실제 프로세스 구동 여부 확인 ───
                if not manager.is_running():
                    print(f"VM {vm.id} ({vm.ip_address}): 프로세스 종료 감지 → stopped")
                    vm_crud.reset_vm_to_stopped(db, vm.id, "stopped")
                    synced.append({"vm_id": vm.id, "result": "stopped"})
                else:
                    # ─── 정상: DB와 실제 상태 일치 ───
                    print(f"VM {vm.id} ({vm.ip_address}): 정상 running 확인")

            except Exception as e:
                # ─── 개별 VM 처리 실패 시 전체 루프 중단 없이 계속 진행 ───
                print(f"VM {vm.id} 체크 중 예외: {e}")
                errors.append({"vm_id": vm.id, "error": str(e)})

        return {"status": "success", "synced": synced, "errors": errors}

    except Exception as e:
        # ─── DB 조회 자체 실패 등 치명적 오류 ───
        print(f"전체 동기화 오류: {e}")
        return {"status": "error", "detail": str(e)}

    finally:
        db.close()