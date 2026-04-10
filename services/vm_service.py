import os
import time
import socket
import shutil
import subprocess
from sqlalchemy.orm import Session
from core.config import settings
from core.vm_manager import VMwareController
from crud import vm_crud
from models.user_model import User
from models.vm_model import VM

# ─────────────────────────────────────────────────────────────────
# 1. DB 기반 다음 사용 가능한 IP 계산
# ─────────────────────────────────────────────────────────────────
def get_next_available_ip(db: Session, base_ip: str, start: int = 122, end: int = 254) -> str:
    """
    DB의 ip_address 컬럼을 기준으로 start~end 범위에서
    사용되지 않은 가장 작은 옥텟의 IP를 반환합니다.

    [DB 기반 방식]
    VM 삭제 시 DB 레코드가 사라지므로, 다음 생성 시
    비어있는 가장 작은 슬롯(123)을 바로 재사용.
    """
    # ─── 1. DB에서 현재 사용 중인 마지막 옥텟 집합 조회 ───
    used_octets = set()
    for vm in db.query(VM).all():
        if vm.ip_address:
            try:
                used_octets.add(int(vm.ip_address.split(".")[-1]))
            except (ValueError, IndexError):
                continue

    # ─── 2. base_ip 앞 3 옥텟 추출 (예: "192.168.137") ───
    prefix = ".".join(base_ip.split(".")[:3])

    # ─── 3. 범위 내 첫 번째 빈 슬롯 선택 ───
    for octet in range(start, end + 1):
        if octet not in used_octets:
            ip = f"{prefix}.{octet}"
            print(f"[IP 할당] 선택: {ip} | 사용 중: {sorted(used_octets)}")
            return ip

    raise RuntimeError(f"할당 가능한 IP 없음 ({prefix}.{start}~{prefix}.{end} 전체 사용 중)")

# ─────────────────────────────────────────────────────────────────
# 2. known_hosts IP 항목 제거 (Utility)
# ─────────────────────────────────────────────────────────────────
def _remove_known_host(ip: str):
    """
    ssh-keygen -R <ip> 를 실행해 ~/.ssh/known_hosts에서
    해당 IP의 호스트 키 핑거프린트를 제거합니다.

    이 작업을 하지 않으면 동일 IP로 새 VM을 생성했을 때
    SSH 접속 시 "Host key verification failed" 오류가 발생합니다.

    실패해도 삭제 프로세스 전체를 중단시키지 않도록
    예외를 내부에서 처리하고 경고 로그만 남깁니다.
    """
    try:
        result = subprocess.run(
            ["ssh-keygen", "-R", ip],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            print(f"[DEBUG] ✅ known_hosts에서 {ip} 제거 완료")
        else:
            # 항목이 원래 없어도 returncode 0이 아닐 수 있으나 무시
            print(f"[DEBUG] known_hosts 제거 결과: {result.stderr.strip()}")
    except FileNotFoundError:
        # Windows 환경 등에서 ssh-keygen이 PATH에 없는 경우
        print(f"[WARN] ssh-keygen 명령을 찾을 수 없습니다. known_hosts 수동 정리 필요: {ip}")
    except Exception as e:
        print(f"[WARN] known_hosts 제거 중 오류 (삭제는 계속 진행): {str(e)}")

# ─────────────────────────────────
# 3. SSH 소켓 가용성 체크 (Utility)
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
# 4. 인프라 전원 제어 (Stop, Reboot, Start)
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
# 5. 인프라 신규 생성 
# ─────────────────────
async def create_new_vm_task(db: Session, user: User, os_type: str):

    base_manager = VMwareController(settings.BASE_VMX)

    # ──────────────────────────
    # 1. 다음 IP 및 경로 계산
    # ──────────────────────────
    next_ip      = get_next_available_ip(db, base_ip=settings.BASE_IP)
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


# ─────────────────────────────────────────────────────────────
# 6. 인프라 삭제 (VMX 폴더 제거 + DB 레코드 삭제 + IP 회수)
# ─────────────────────────────────────────────────────────────
async def delete_vm_task(db: Session, vm_id: int):
    """
    가상머신을 완전히 삭제합니다.
    순서: VM 강제 종료 → VMX 폴더 삭제 → DB 레코드 제거
    IP는 DB 레코드가 사라지면 자동으로 '사용 가능' 상태로 회수됩니다.
    (get_next_ip가 DB에 없는 IP를 다음 후보로 선택하는 방식)
    """

    print(f"\n[DEBUG] === VM 삭제 시작 (VM ID: {vm_id}) ===")

    # ─── 1. DB에서 VM 정보 조회 ───
    db_vm = db.query(VM).filter(VM.id == vm_id).first()

    if not db_vm:
        print(f"[DEBUG] ❌ 에러: DB에서 VM을 찾을 수 없습니다.")
        return {"status": "error", "message": "VM not found"}

    # ─── 2. 삭제 진행 중 상태로 변경 (UI 잠금용) ───
    vm_crud.update_vm_status(db, vm_id, "deleting")

    try:
        # ─── 3. VMX 경로 계산 ───
        last_octet   = db_vm.ip_address.split(".")[-1]
        specific_dir = os.path.join(settings.CLONE_ROOT, f"Clone_{last_octet}")
        vmx_path     = os.path.join(specific_dir, f"Clone_{last_octet}.vmx")

        # ─── 4. VM이 실행 중이면 강제 종료 (파일 잠금 해제) ───
        if os.path.exists(vmx_path):
            manager = VMwareController(vmx_path)

            if manager.is_running():
                print(f"[DEBUG] VM 실행 중 감지 → 강제 종료(hard stop) 실행")
                manager.stop(mode="hard")

                # 프로세스 종료 대기 (최대 30초)
                for _ in range(6):
                    if not manager.is_running():
                        break
                    time.sleep(5)

            # ─── 5. VMX 폴더 전체 삭제 ───
            print(f"[DEBUG] 폴더 삭제: {specific_dir}")
            shutil.rmtree(specific_dir, ignore_errors=True)
        else:
            # VMX 파일이 이미 없어도 DB 정리는 계속 진행
            print(f"[DEBUG] VMX 폴더 없음 (이미 삭제됨): {specific_dir}")

        # ─── 5-1. known_hosts에서 해당 IP 항목 제거 ───
        _remove_known_host(db_vm.ip_address)

        # ─── 6. DB 레코드 삭제 (= IP 자동 회수) ───
        print(f"[DEBUG] DB 레코드 삭제 (IP 회수): {db_vm.ip_address}")
        vm_crud.delete_vm(db, vm_id)

        print(f"[DEBUG] ✅ VM 삭제 완료 (IP {db_vm.ip_address} 회수됨)")
        return {"status": "success"}

    except Exception as e:
        print(f"[DEBUG] ❌ 삭제 중 예외 발생: {str(e)}")
        # ─── 삭제 실패 시 error 상태로 복구 (레코드는 유지) ───
        vm_crud.update_vm_status(db, vm_id, "error")
        return {"status": "error", "message": f"삭제 실패: {str(e)}"}