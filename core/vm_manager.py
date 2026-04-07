import subprocess
import time
import os
import re
import glob
import paramiko

class VMwareController:
    # ──────────────────────────────────────────────────────────────────────
    # VMware Workstation 가상머신을 제어하고 네트워크 설정을 자동화하는 컨트롤러.
    # ──────────────────────────────────────────────────────────────────────

    def __init__(self, vmx_path):
        # ────────────────────────────────
        # VMX 파일 존재 확인 및 경로 초기화.
        # ────────────────────────────────
        if not os.path.exists(vmx_path):
            raise FileNotFoundError(f"VMX 파일을 찾을 수 없습니다: {vmx_path}")
        self.vmx_path = vmx_path
        self.vmx_bin = "vmrun"
    
    def _run_vmrun(self, args):
        # ────────────────────────────────────
        # vmrun 명령어 실행을 위한 내부 유틸리티.
        # ────────────────────────────────────
        
        main_cmd = args[0]

        if main_cmd == "clone":
            command = [self.vmx_bin, "-T", "ws", "clone"] + args[1:]
        else:
            command = [self.vmx_bin, "-T", "ws", main_cmd, self.vmx_path] + args[1:]

        try:
            result = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
                shell=False
            )
            return result.stdout.decode("utf-8", errors="ignore").strip()
        except subprocess.CalledProcessError as e:
            err_msg = e.stderr.decode("utf-8", errors="ignore").strip()
            if err_msg:
                print(f"[vmrun Error] {main_cmd}: {err_msg}")
            return None

    def _run_ssh(self, ip, username, password, command, timeout=30):
        # ────────────────────────────
        # SSH를 통한 원격 명령어 실행.
        # ────────────────────────────
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            client.connect(
                hostname=ip,
                username=username,
                password=password,
                timeout=timeout,
                banner_timeout=timeout,
                allow_agent=False,
                look_for_keys=False
            )
            stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
            out = stdout.read().decode("utf-8", errors="ignore").strip()
            err = stderr.read().decode("utf-8", errors="ignore").strip()
            if err:
                print(f"[SSH stderr] {err}")
            return out
        except Exception as e:
            print(f"[SSH Error] {ip} → {e}")
            return None
        finally:
            client.close()

    def _wait_ssh(self, ip, username, password, timeout=120):
        # ────────────────────────────────────
        # 부팅 완료 확인을 위한 SSH 접속 대기.
        # ────────────────────────────────────
        print(f"SSH 접속 대기 중... ({ip})")
        start = time.time()
        while time.time() - start < timeout:
            try:
                client = paramiko.SSHClient()
                client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                client.connect(ip, username=username, password=password,
                                timeout=5, allow_agent=False, look_for_keys=False)
                client.close()
                print(f"SSH 접속 성공: {ip}")
                return True
            except Exception:
                time.sleep(5)
        print(f"SSH 접속 타임아웃: {ip}")
        return False

    def _inject_vmx_settings(self, vmx_path):\
        # ──────────────────────────────────────
        # VMX 파일에 UUID 및 MAC 생성 설정 주입.
        # ──────────────────────────────────────
        with open(vmx_path, "r", encoding="utf-8") as f:
            content = f.read()

        content = re.sub(r'^uuid\.bios\s*=.*\n', '', content, flags=re.MULTILINE)
        content = re.sub(r'^uuid\.location\s*=.*\n', '', content, flags=re.MULTILINE)

        content = re.sub(r'^ethernet0\.generatedAddress\s*=.*\n', '', content, flags=re.MULTILINE)
        content = re.sub(r'^ethernet0\.generatedAddressOffset\s*=.*\n', '', content, flags=re.MULTILINE)
        content = re.sub(r'^ethernet0\.addressType\s*=.*\n', '', content, flags=re.MULTILINE)
        content += '\nethernet0.addressType = "generated"'

        settings = {
            'uuid.action': 'create',
            'msg.autoAnswer': 'TRUE'
        }
        for key, value in settings.items():
            if f'{key} = ' not in content:
                content += f'\n{key} = "{value}"'
                print(f"VMX 설정 주입: {key} = {value}")
            else:
                print(f"VMX 설정 이미 존재: {key}")

        with open(vmx_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"VMX 설정 주입 완료: {os.path.basename(vmx_path)}")

    def start(self):
        # ────────────────────────
        # VM 시작.
        # ────────────────────────
        print(f"Starting VM: {os.path.basename(self.vmx_path)}")
        return self._run_vmrun(["start", "nogui"])

    def stop(self, mode="soft"):
        # ────────────────────────
        # VM 종료.
        # ────────────────────────
        print(f"Stopping VM: {os.path.basename(self.vmx_path)}")
        return self._run_vmrun(["stop", mode])

    def get_ip(self, timeout=120, check_ip=None):
        # ────────────────────────
        # 게스트 OS IP 획득.
        # ────────────────────────
        start_time = time.time()
        print("VMware Tools IP 대기 중...")
        while time.time() - start_time < timeout:
            ip = self._run_vmrun(["getGuestIPAddress"])
            if ip and re.match(r"^\d{1,3}(\.\d{1,3}){3}$", ip):
                return ip

            if self._check_port_open(check_ip, 22):
                print(f"💡 VMware Tools는 묵묵부답이나, {check_ip}번 SSH 포트가 활성화되었습니다.")
                return check_ip
            
            time.sleep(5)
        return None

    def clone(self, new_vmx_path):
        # ──────────────────────────────
        # VM 전체 복제 및 설정 주입.
        # ──────────────────────────────
        import shutil
        new_dir = os.path.dirname(new_vmx_path)

        if os.path.exists(new_dir):
            print(f"기존 Clone 폴더 삭제: {new_dir}")
            shutil.rmtree(new_dir)
        os.makedirs(new_dir)

        result = self._run_vmrun(["clone", self.vmx_path, new_vmx_path, "full"])

        if result is not None and os.path.exists(new_vmx_path):
            self._inject_vmx_settings(new_vmx_path)

            time.sleep(2)
        return result

    def get_next_ip(self, clone_root_dir, base_ip):
        # ───────────────────────────────────────────
        # 기존 폴더 확인 후 다음 사용 가능한 IP 계산.
        # ───────────────────────────────────────────
        folders = glob.glob(os.path.join(clone_root_dir, "Clone_*"))
        if not folders:
            return self._increment_ip(base_ip)
        existing_nums = []
        for f in folders:
            try:
                num = int(os.path.basename(f).split("_")[-1])
                existing_nums.append(num)
            except:
                continue
        next_num = max(existing_nums) + 1 if existing_nums else 122
        parts = base_ip.split(".")
        parts[-1] = str(next_num)
        return ".".join(parts)

    def _increment_ip(self, base_ip):
        # ───────────────────────────────────────────
        # IP의 마지막 옥텟을 1 증가시킴 (내부 메서드).
        # ───────────────────────────────────────────
        parts = base_ip.split(".")
        parts[-1] = str(int(parts[-1]) + 1)
        return ".".join(parts)

    def set_static_ip(self, current_ip, guest_user, guest_pw, new_ip,gate_ip, subnet_mask, interface):
        # ─────────────────────────────────────────────────
        # Linux NetworkManager 설정을 통한 고정 IP 주입.
        # ─────────────────────────────────────────────────
        if not self._wait_ssh(current_ip, guest_user, guest_pw):
            print("❌ SSH 접속 실패 - IP 변경 불가")
            return None

        target_file = f"/etc/NetworkManager/system-connections/{interface}.nmconnection"

        cmd = (
            f"sed -i 's/^address1=.*/address1={new_ip}\\/{subnet_mask},{gate_ip}/' {target_file} && "
            f"sed -i '/^uuid=/d' {target_file} && "
            f"chmod 600 {target_file} && "
            f"nmcli connection reload && "
            f"nmcli device reapply {interface} || true"
        )

        print(f"SSH로 IP 변경 중: {current_ip} → {new_ip}")
        result = self._run_ssh(current_ip, guest_user, guest_pw, cmd)
        print(f"IP 변경 명령 완료: {result}")
        return result

    def regenerate_ssh_hostkey(self, ip, guest_user, guest_pw):
        # ───────────────────────────────
        # SSH 호스트 키 재생성.
        # ───────────────────────────────
        cmd = (
            "rm -f /etc/ssh/ssh_host_* && "
            "ssh-keygen -A && "
            "systemctl restart sshd"
        )
        print(f"SSH host key 재생성 중: {ip}")
        return self._run_ssh(ip, guest_user, guest_pw, cmd)
    
    def _check_port_open(self, ip, port):
        # ───────────────────────────────
        # 특정 포트 통신 가능 여부 확인.
        # ───────────────────────────────
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex((ip, port))
        sock.close()
        return result == 0
    