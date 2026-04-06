import subprocess
import time
import os
import re
import glob

class VMwareController:
    def __init__(self, vmx_path):
        if not os.path.exists(vmx_path):
            raise FileNotFoundError(f"VMX 파일을 찾을 수 없습니다: {vmx_path}")
        self.vmx_path = vmx_path
        self.vmx_bin = "vmrun"

    def _run_command(self, args):
        main_cmd = args[0]
        # 명령어 종류에 따라 인자 배치를 다르게 합니다.
        if main_cmd == "clone":
            command = [self.vmx_bin, "-T", "ws", "clone"] + args[1:]
        elif main_cmd == "runProgramInGuest":
            # runProgramInGuest는 vmx_path가 명령어 바로 뒤에 와야 함
            command = [self.vmx_bin, "-T", "ws", "runProgramInGuest", self.vmx_path] + args[1:]
        else:
            # start, stop, getGuestIPAddress 등 일반 명령어
            command = [self.vmx_bin, "-T", "ws", main_cmd, self.vmx_path] + args[1:]

        try:
            result = subprocess.run(
                command, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE, 
                check=True, 
                shell=False
            )
            return result.stdout.decode('utf-8', errors='ignore').strip()
        except subprocess.CalledProcessError as e:
            err_msg = e.stderr.decode('utf-8', errors='ignore').strip()
            # 에러 메시지가 비어있지 않을 때만 출력 (루프 중 불필요한 출력 방지)
            if err_msg:
                print(f"[VMwareController Error] Command: {main_cmd}, Message: {err_msg}")
            return None
        
    def start(self):
        print(f"Starting VM: {os.path.basename(self.vmx_path)}")
        return self._run_command(["start", "nogui"])
    
    def get_ip(self, timeout=120): # 타임아웃을 120초로 늘림
        start_time = time.time()
        print(f"Waiting for VMware Tools to start...")
        while time.time() - start_time < timeout:
            ip = self._run_command(["getGuestIPAddress"])
            # IP 형식이 맞는지 확인
            if ip and re.match(r"^\d{1,3}(\.\d{1,3}){3}$", ip):
                return ip
            time.sleep(5)
        return None

    def clone(self, new_vmx_path):
        new_dir = os.path.dirname(new_vmx_path)
        if not os.path.exists(new_dir):
            os.makedirs(new_dir)
        return self._run_command(["clone", self.vmx_path, new_vmx_path, "full"])

    def get_next_ip(self, clone_root_dir, base_ip="192.168.111.121"):
        folders = glob.glob(os.path.join(clone_root_dir, "Clone_*"))
        if not folders:
            return self._increment_ip(base_ip)
        existing_nums = []
        for f in folders:
            try:
                num = int(os.path.basename(f).split('_')[-1])
                existing_nums.append(num)
            except: continue
        next_num = max(existing_nums) + 1 if existing_nums else 122
        parts = base_ip.split('.')
        parts[-1] = str(next_num)
        return '.'.join(parts)

    def _increment_ip(self, base_ip):
        parts = base_ip.split('.')
        parts[-1] = str(int(parts[-1]) + 1)
        return '.'.join(parts)

    def set_static_ip(self, guest_user, guest_pw, new_ip):
        target_file = "/etc/NetworkManager/system-connections/ens160.nmconnection"
        
        # 1. IP 수정 및 UUID 삭제
        sed_cmd = f"sed -i 's/^address1=.*/address1={new_ip}\\/24,192.168.111.2/' {target_file} && sed -i '/^uuid=/d' {target_file}"
        chmod_cmd = f"chmod 600 {target_file}"
        
        # 2. 물리적 장치 재적용 (이 명령어가 핵심입니다)
        # reload -> 장치에 강제 적용 -> 연결 업
        net_restart_cmd = "nmcli connection reload && nmcli device reapply ens160 && nmcli connection up ens160"
        
        full_cmd = f"{sed_cmd} && {chmod_cmd} && {net_restart_cmd}"
        
        print(f"DEBUG - IP 강제 주입 및 장치 재적용 시도: {new_ip}")
        
        return self._run_command([
            "runProgramInGuest",
            "-guestUser", guest_user,
            "-guestPassword", guest_pw,
            "/bin/bash", "-c", full_cmd
        ])