import os
import time
from dotenv import load_dotenv
from core.vm_manager import VMwareController
from sqlalchemy.orm import Session
from crud import vm as vm_crud
from models.user_model import User

async def create_new_vm_task(db: Session, user: User, os_type: str):

    # ───────────────────
    # 설정 영역
    # ───────────────────
    BASE_VMX   = os.getenv("BASE_VMX")
    CLONE_ROOT = os.getenv("CLONE_ROOT")
    GUEST_USER = os.getenv("GUEST_USER")
    GUEST_PW   = os.getenv("GUEST_PW")
    BASE_IP    = os.getenv("BASE_IP")
    GATE_IP    = os.getenv("GATE_IP")
    SUBNET_MASK = os.getenv("SUBNET_MASK")
    INTERFACE   = os.getenv("INTERFACE")

    base_manager = VMwareController(BASE_VMX)

    # ──────────────────────────
    # 1. 다음 IP 및 경로 계산
    # ──────────────────────────
    next_ip      = base_manager.get_next_ip(CLONE_ROOT, base_ip=BASE_IP)
    last_octet   = next_ip.split(".")[-1]
    specific_dir = os.path.join(CLONE_ROOT, f"Clone_{last_octet}")
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
        current_ip = new_vm.get_ip(timeout=120, check_ip=BASE_IP)
        print(f"부팅 완료. 현재 IP: {current_ip}")

        if not current_ip:
            raise Exception("IP 획득 실패")
        
        # ──────────────────────────────────────────────
        # 5. SSH host key 재생성 (Clone 간 충돌 방지)
        # ──────────────────────────────────────────────
        new_vm.regenerate_ssh_hostkey(current_ip, GUEST_USER, GUEST_PW)


        # ────────────────────────
        # 6. SSH로 IP 변경
        # ────────────────────────
        new_vm.set_static_ip(
            current_ip, GUEST_USER, GUEST_PW,
            next_ip,GATE_IP,SUBNET_MASK, INTERFACE
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
        if new_vm._wait_ssh(next_ip, GUEST_USER, GUEST_PW, timeout=60):
            print(f"✅ 완료! 서버 IP: {next_ip}")
            print(f"   접속: ssh {GUEST_USER}@{next_ip}")
            vm_crud.update_vm_status(db, vm_id=db_vm.id, status="running")
        else:
            print(f"⚠️ 재부팅 후 SSH 접속 안 됨. IP 설정을 수동으로 확인하세요.")
            vm_crud.update_vm_status(db, vm_id=db_vm.id, status="network_error")

    except Exception as e:
        print(f"VM 생성 중 오류 발생: {e}")
        vm_crud.update_vm_status(db, vm_id=db_vm.id, status="failed")