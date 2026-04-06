import os
import time
from vm_controller import VMwareController

if __name__ == "__main__":
    # --- 설정 영역 ---
    BASE_VMX = r"d:\01_WORK\02_Study\10_Linux\Rocky9\CloudeServer\CloudeServer.vmx"
    CLONE_ROOT = r"d:\01_WORK\02_Study\10_Linux\Rocky9\CloneServer"
    GUEST_PW = "" 
    # ----------------

    base_manager = VMwareController(BASE_VMX)

    # 1. 다음 IP 및 경로 계산
    next_ip = base_manager.get_next_ip(CLONE_ROOT)
    last_octet = next_ip.split('.')[-1]
    
    specific_dir = os.path.join(CLONE_ROOT, f"Clone_{last_octet}")
    new_vmx_path = os.path.join(specific_dir, f"Clone_{last_octet}.vmx")

    print(f"=== 신규 클라우드 서버 생성 시나리오 시작: {next_ip} ===")

    # 2. 복제 실행
    # clone 메서드 내부에서 폴더를 생성하도록 수정되었습니다.
    if base_manager.clone(new_vmx_path) is not None:
        new_vm = VMwareController(new_vmx_path)
        
        # 3. 새 VM 시작
        if new_vm.start() is not None:
            print(f"VM이 부팅될 때까지 대기합니다... (Target: {next_ip})")
            current_ip = new_vm.get_ip(timeout=100)

            if current_ip:
                print(f"부팅 확인됨. 내부 설정을 {next_ip}로 변경합니다.")
                new_vm.set_static_ip("root", GUEST_PW, next_ip)
                
                print("설정 적용을 위해 VM을 재부팅합니다... (가장 확실한 방법)")
                new_vm._run_command(["rebootGuest"])

                print("재부팅 완료 대기 중... (60초)")
                time.sleep(20)

                final_ip = new_vm.get_ip(timeout=60)
                
                if final_ip == next_ip:
                    print(f"✅ 모든 공정 완료! 서버 IP: {final_ip}")
                else:
                    print(f"⚠️ 여전히 IP가 {final_ip}입니다. 원본 VM의 네트워크 설정을 확인하세요.")
    else:
        print("❌ 복제 단계에서 실패했습니다. 원본 VM이 켜져 있는지 혹은 경로 권한을 확인하세요.")