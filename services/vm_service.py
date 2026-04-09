import os
import time
import socket
from sqlalchemy.orm import Session
from core.config import settings
from core.vm_manager import VMwareController
from crud import vm_crud
from models.user_model import User
from models.vm_model import VM

# ─────────────────────────────────
# 1. SSH 소켓 가용성 체크 (Utility)
# ─────────────────────────────────
def check_ssh_socket(ip, port=22, timeout=2):
    """
    특정 IP의 SSH 포트(22)가 열려있는지 단순 TCP 연결로 확인합니다.
    """
    try:
        with socket.create_connection((ip,port), timeout= timeout):
            return True
    except:
        return False

# ────────────────────────────────────────────────
# 1. 인프라 전원 제어 (Stop, Reboot, Start)
# ────────────────────────────────────────────────
async def control_vm_power(db: Session, vm_id: int, action: str):
    """
    가상머신의 전원 상태를 제어하고, 실제 상태와 DB 상태를 동기화합니다.
    """

    print(f"\n[DEBUG] === 전원 제어 시작 (VM ID: {vm_id}, Action: {action}) ===")

    # ─── 1. DB에서 VM 정보 조회 ───
    db_vm = db.query(VM).filter(VM.id == vm_id).first()

    if not db_vm:
        print(f"[DEBUG] ❌ 에러: DB에서 VM을 찾을 수 없습니다.")
        return {"status": "error", "message": "VM not found"}

    try:
        # ─── 2. VMX 경로 계산 및 존재 확인 ───
        last_octet = db_vm.ip_address.split(".")[-1]
        specific_dir = os.path.join(settings.CLONE_ROOT, f"Clone_{last_octet}")
        vmx_path = os.path.join(specific_dir, f"Clone_{last_octet}.vmx")

        if not os.path.exists(vmx_path):
            raise Exception(f"VMX 파일이 없습니다: {vmx_path}")

        manager = VMwareController(vmx_path)

        # ─── 3. 실제 구동 상태와 DB 상태 동기화 ───
        actual_running = manager.is_running()
        if not actual_running and db_vm.status == "running":
            vm_crud.update_vm_status(db, vm_id, "stopped")
            db.refresh(db_vm)

        # ─── 4. Action별 제어 로직 ───

        # [CASE: START]
        if action == "start":
            vm_crud.update_vm_status(db, vm_id, "starting")
            manager.start()

            # SSH 접속 가능할 때까지 대기 (최대 2분)
            for _ in range(24):
                if check_ssh_socket(db_vm.ip_address):
                    vm_crud.update_vm_status(db, vm_id, "running")
                    return {"status": "success"}
                time.sleep(5)
            raise Exception("ssh 대기 시간 초과")

        # [CASE: STOP]
        elif "stop" in action:
            vm_crud.update_vm_status(db, vm_id, "stopping")
            mode = "hard" if "hard" in action else "soft"
            manager.stop(mode = mode)

            # 프로세스가 완전히 종료될 때까지 대기
            for _ in range(10):
                if not manager.is_running(): break
                time.sleep(5)
            vm_crud.update_vm_status(db, vm_id, "stopped")

        # [CASE: REBOOT]
        elif "reboot" in action:
            vm_crud.update_vm_status(db, vm_id, "rebooting")
            mode = "hard" if "hard" in action else "soft"
            manager.reset(mode = mode)

            # 재부팅 후 SSH 재연결 확인
            time.sleep(10)
            for _ in range(24):
                if check_ssh_socket(db_vm.ip_address):
                    vm_crud.update_vm_status(db, vm_id, "running")
                    return {"status": "success"}
                time.sleep(5)

        return {"status": "success"}
    
    except Exception as e:
        print(f"[DEBUG] ❌ 예외 발생: {str(e)}")
        vm_crud.update_vm_status(db, vm_id, "error")
        return {"status": "error", "message": f"시스템 오류: {str(e)}"}
    
# ─────────────────────
# 2. 인프라 신규 생성 
# ─────────────────────
async def create_new_vm_task(db: Session, user: User, os_type: str):

    base_manager = VMwareController(settings.BASE_VMX)

    # ──────────────────────────
    # 1. 다음 IP 및 경로 계산
    # ──────────────────────────
    next_ip      = base_manager.get_next_ip(settings.CLONE_ROOT, base_ip=settings.BASE_IP)
    last_octet   = next_ip.split(".")[-1]
    specific_dir = os.path.join(settings.CLONE_ROOT, f"Clone_{last_octet}")
    new_vmx_path = os.path.join(specific_dir, f"Clone_{last_octet}.vmx")

    print(f"=== 신규 클라우드 서버 생성 시작: {next_ip} ===")

    # ─────────────────────────────────────────────────────────────
    # 2. 복제 (기존 폴더 있으면 자동 삭제 후 재생성 + VMX 설정 주입)
    # ─────────────────────────────────────────────────────────────

    db_vm = vm_crud.create_vm(
        db=db,
        owner_id=user.id,
        ip = next_ip,
        os = os_type,
        status = "creating"
    )

    try:        
        # ───────────────
        # 3. VM 부팅
        # ───────────────
        if base_manager.clone(new_vmx_path) is None:
            raise Exception("❌ 복제 실패.")       

        new_vm = VMwareController(new_vmx_path)
        new_vm.start()
        print("VM 부팅 대기 중...")

        # ───────────────
        # 4. IP 획득 
        # ───────────────
        current_ip = new_vm.get_ip(timeout=120, check_ip=settings.BASE_IP)
        print(f"부팅 완료. 현재 IP: {current_ip}")

        if not current_ip:
            raise Exception("IP 획득 실패")
        
        # ──────────────────────────────────────────────
        # 5. SSH host key 재생성 (Clone 간 충돌 방지)
        # ──────────────────────────────────────────────
        new_vm.regenerate_ssh_hostkey(current_ip, settings.GUEST_USER, settings.GUEST_PW)


        # ────────────────────────
        # 6. SSH로 IP 변경
        # ────────────────────────
        new_vm.set_static_ip(
            current_ip, settings.GUEST_USER, settings.GUEST_PW,
            next_ip, settings.GATE_IP, settings.SUBNET_MASK, settings.INTERFACE
        )

        # ───────────────────
        # 7. 재부팅
        # ───────────────────   
        print("설정 적용을 위해 재부팅 중...") 
        new_vm._run_vmrun(["rebootGuest"])
        time.sleep(20)

        # ──────────────────────────────
        # 8. 새 IP로 SSH 접속 확인
        # ──────────────────────────────
        if new_vm._wait_ssh(next_ip, settings.GUEST_USER, settings.GUEST_PW, timeout=60):
            print(f"✅ 완료! 서버 IP: {next_ip}")
            print(f"   접속: ssh {settings.GUEST_USER}@{next_ip}")
            vm_crud.update_vm_status(db, vm_id=db_vm.id, status="running")
        else:
            print(f"⚠️ 재부팅 후 SSH 접속 안 됨. IP 설정을 수동으로 확인하세요.")
            vm_crud.update_vm_status(db, vm_id=db_vm.id, status="network_error")

    except Exception as e:
        print(f"VM 생성 중 오류 발생: {e}")
        vm_crud.update_vm_status(db, vm_id=db_vm.id, status="failed")