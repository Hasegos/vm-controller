import subprocess
import time
import socket
import shutil
import os
import re
import math
import paramiko
from io import StringIO
from core.config import settings

class VMwareController:
    # ──────────────────────────────────────────────────────────────────────
    # VMware Workstation 가상머신을 제어하고 네트워크 설정을 자동화하는 컨트롤러.
    # ──────────────────────────────────────────────────────────────────────

    def __init__(self, vmx_path):
        # ────────────────────────────────
        # 1.VMX 파일 존재 확인 및 경로 초기화.
        # ────────────────────────────────
        if not os.path.exists(vmx_path):
            raise FileNotFoundError(f"VMX 파일을 찾을 수 없습니다: {vmx_path}")
        self.vmx_path = vmx_path
        self.vmx_bin = "vmrun"
    
    def _run_vmrun(self, args):
        # ────────────────────────────────────
        # 2.vmrun 명령어 실행을 위한 내부 유틸리티.
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
        
    def _run_ssh(self, ip, username, command, password=None, pkey_str=None, timeout=30):
        # ────────────────────────────
        # 3.SSH를 통한 원격 명령어 실행.
        # ────────────────────────────
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        try:
            connect_kwargs = dict(
                hostname=ip,
                username=username,
                password=password,
                timeout=timeout,
                banner_timeout=timeout,
                allow_agent=False,
                look_for_keys=False
            )

            if pkey_str:
                # ─── PEM 키 문자열을 paramiko RSAKey 객체로 변환 ───
                pkey = paramiko.RSAKey.from_private_key(StringIO(pkey_str))
                connect_kwargs["pkey"] = pkey
            else:
                # ─── 패스워드 방식 (최초 공개키 주입 시에만 사용) ───
                connect_kwargs["password"] = password

            client.connect(**connect_kwargs)
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

    def _wait_ssh(self, ip, username, password=None, pkey_str=None, timeout=120):
        # ────────────────────────────────────
        # 4. 부팅 완료 확인을 위한 SSH 접속 대기.
        #    pkey_str 우선, 없으면 password fallback
        # ────────────────────────────────────
        print(f"SSH 접속 대기 중... ({ip})")
        start = time.time()
        while time.time() - start < timeout:
            try:
                client = paramiko.SSHClient()
                client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

                connect_kwargs = dict(
                    hostname=ip,
                    username=username,
                    timeout=5,
                    allow_agent=False,
                    look_for_keys=False
                )
                if pkey_str:
                    pkey = paramiko.RSAKey.from_private_key(StringIO(pkey_str))
                    connect_kwargs["pkey"] = pkey
                else:
                    connect_kwargs["password"] = password

                client.connect(**connect_kwargs)
                client.close()

                print(f"SSH 접속 성공: {ip}")
                return True
            
            except Exception:
                time.sleep(5)

        print(f"SSH 접속 타임아웃: {ip}")
        return False
    
    # ──────────────────────────────────────────────────────────────────────
    # 5. 게스트 OS 원본 VMX에서 리소스 스펙 파싱
    # BASE_VMX 기준으로 numvcpus, memsize를 읽어 70% 상한값을 계산합니다.
    # ──────────────────────────────────────────────────────────────────────
    def _parse_base_resources(self):
        """
        BASE_VMX 파일에서 numvcpus, memsize를 파싱하여 반환합니다.
        파싱 실패 시 안전한 기본값(cpu=1, mem=1024)을 반환합니다.
        """
        base_vmx = settings.BASE_VMX
        cpu  = 1
        mem  = 1024  # MB

        try:
            with open(base_vmx, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()

                    if line.lower().startswith("numvcpus"):
                        match = re.search(r'=\s*"?(\d+)"?', line)

                        if match:
                            cpu = int(match.group(1))

                    elif line.lower().startswith("memsize"):
                        match = re.search(r'=\s*"?(\d+)"?', line)

                        if match:
                            mem = int(match.group(1))
        except Exception as e:
            print(f"[WARN] BASE VMX 리소스 파싱 실패, 기본값 사용: {e}")

        ratio = settings.RESOURCE_LIMIT_RATIO

        # ─── 최솟값 1 보장 (floor(1 × 0.7) = 0 방지) ───
        limited_cpu = max(1, math.floor(cpu * ratio))

        # ─── VMware는 memsize를 반드시 4의 배수로 요구 ───
        raw_mem     = math.floor(mem * ratio)
        limited_mem = max(512, (raw_mem // 4) * 4)

        print(f"[리소스 상한] 원본 CPU:{cpu} → {limited_cpu} | 원본 MEM:{mem}MB → {limited_mem}MB (비율: {ratio})")
        return limited_cpu, limited_mem

    def _inject_vmx_settings(self, vmx_path):
        # ──────────────────────────────────────
        # 6.VMX 파일에 UUID 및 MAC 생성 설정 주입.
        # ──────────────────────────────────────
        with open(vmx_path, "r", encoding="utf-8") as f:
            content = f.read()

        # ─── UUID/MAC 관련 기존 설정 제거 ───
        content = re.sub(r'^uuid\.bios\s*=.*\n',                    '', content, flags=re.MULTILINE)
        content = re.sub(r'^uuid\.location\s*=.*\n',                '', content, flags=re.MULTILINE)
        content = re.sub(r'^ethernet0\.generatedAddress\s*=.*\n',   '', content, flags=re.MULTILINE)
        content = re.sub(r'^ethernet0\.generatedAddressOffset\s*=.*\n', '', content, flags=re.MULTILINE)
        content = re.sub(r'^ethernet0\.addressType\s*=.*\n',        '', content, flags=re.MULTILINE)
        content += '\nethernet0.addressType = "generated"'

        # ─── 기본 동작 설정 주입 ───
        vm_settings = {
            'uuid.action': 'create',
            'msg.autoAnswer': 'TRUE'
        }

        for key, value in vm_settings.items():
            if f'{key} = ' not in content:
                content += f'\n{key} = "{value}"'
                print(f"VMX 설정 주입: {key} = {value}")
            else:
                print(f"VMX 설정 이미 존재: {key}")


        # ─── 리소스 상한 주입 (게스트 OS 원본의 70%) ───
        limited_cpu, limited_mem = self._parse_base_resources()

        # ─── numvcpus 교체 또는 추가 ───
        if re.search(r'^numvcpus\s*=', content, flags=re.MULTILINE):
            content = re.sub(r'^numvcpus\s*=.*', f'numvcpus = "{limited_cpu}"', content, flags=re.MULTILINE)
        else:
            content += f'\nnumvcpus = "{limited_cpu}"'

        # ─── memsize 교체 또는 추가 ───
        if re.search(r'^memsize\s*=', content, flags=re.MULTILINE):
            content = re.sub(r'^memsize\s*=.*', f'memsize = "{limited_mem}"', content, flags=re.MULTILINE)
        else:
            content += f'\nmemsize = "{limited_mem}"'

        print(f"VMX 리소스 상한 주입 완료: CPU={limited_cpu}, MEM={limited_mem}MB")

        with open(vmx_path, "w", encoding="utf-8") as f:
            f.write(content)

        print(f"VMX 설정 주입 완료: {os.path.basename(vmx_path)}")

    def start(self):
        # ────────────────────────
        # 7.VM 시작.
        # ────────────────────────
        print(f"Starting VM: {os.path.basename(self.vmx_path)}")
        return self._run_vmrun(["start", "nogui"])

    def stop(self, mode="soft"):
        # ────────────────────────
        # 8.VM 종료.
        # ────────────────────────
        print(f"Stopping VM: {os.path.basename(self.vmx_path)}")
        return self._run_vmrun(["stop", mode])

    def reset(self, mode="soft"):
        # ─────────────────────
        # 9. VM 재시작 (Reset)
        # ─────────────────────
        print(f"Resetting VM ({mode}): {os.path.basename(self.vmx_path)}")
        return self._run_vmrun(["reset", mode])

    def get_ip(self, timeout=120, check_ip=None):
        # ────────────────────────
        # 10.게스트 OS IP 획득.
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
        # 11.VM 전체 복제 및 설정 주입.
        # ──────────────────────────────
        new_dir = os.path.dirname(new_vmx_path)

        if os.path.exists(new_dir):
            print(f"기존 Clone 폴더 삭제: {new_dir}")
            shutil.rmtree(new_dir)
        os.makedirs(new_dir)

        result = self._run_vmrun(["clone", self.vmx_path, new_vmx_path, "full"])

        if result is not None and os.path.exists(new_vmx_path):
            # 리소스 상한 포함한 VMX 설정 주입 
            self._inject_vmx_settings(new_vmx_path)
            time.sleep(2)
        return result

    def set_static_ip(self, current_ip, guest_user, new_ip,gate_ip, subnet_mask, interface,
                    password=None, pkey_str=None):
        # ─────────────────────────────────────────────────
        # 12.Linux NetworkManager 설정을 통한 고정 IP 주입.
        # pkey_str 우선, 없으면 password fallback (최초 주입 시)
        # ─────────────────────────────────────────────────
        if not self._wait_ssh(current_ip, guest_user, password=password, pkey_str=pkey_str):
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
        result = self._run_ssh(current_ip, guest_user, cmd, password=password, pkey_str=pkey_str)
        print(f"IP 변경 명령 완료: {result}")
        return result

    def regenerate_ssh_hostkey(self, ip, guest_user, password=None, pkey_str=None):
        # ───────────────────────────────
        # 13.SSH 호스트 키 재생성.
        # ───────────────────────────────
        cmd = (
            "rm -f /etc/ssh/ssh_host_* && "
            "ssh-keygen -A && "
            "systemctl restart sshd"
        )
        print(f"SSH host key 재생성 중: {ip}")
        return self._run_ssh(ip, guest_user, cmd, password=password, pkey_str=pkey_str)
    
    def inject_public_key(self, ip, guest_user, guest_pw, public_key_str):
        # ──────────────────────────
        # 14.게스트 OS에 공개키 주입
        # ──────────────────────────
        cmd = (
            f"mkdir -p ~/.ssh && "
            f"chmod 700 ~/.ssh && "
            f"echo '{public_key_str}' >> ~/.ssh/authorized_keys && "
            f"chmod 600 ~/.ssh/authorized_keys && "
            # ─── 패스워드 로그인 비활성화 (PEM 전환 완료 후 보안 강화) ───
            f"sed -i 's/^#*PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config && "
            f"systemctl reload sshd"
        )

        print(f"공개키 주입 중: {ip}")
        return self._run_ssh(ip, guest_user, cmd, password=guest_pw)
    
    def get_host_pubkey(self, ip, guest_user, pkey_str):
        # ───────────────────────────────────
        # 15. SSH 호스트 키 fingerprint 조회
        # ───────────────────────────────────
        cmd = (
            "cat /etc/ssh/ssh_host_ed25519_key.pub 2>/dev/null || "
            "cat /etc/ssh/ssh_host_rsa_key.pub"
        )
        result = self._run_ssh(ip, guest_user, cmd, pkey_str=pkey_str)
        if result:
            # ─── 출력 형식: "ssh-ed25519 AAAA... comment" ───
            parts = result.split()
            if len(parts) >= 2:
                known_hosts_line = f"{ip} {parts[0]} {parts[1]}"
                print(f"호스트 fingerprint 획득: {parts[0]}")
                return known_hosts_line
        print(f"[WARN] fingerprint 획득 실패: {ip}")
        return None

    def _check_port_open(self, ip, port):
        # ───────────────────────────────
        # 16.특정 포트 통신 가능 여부 확인.
        # ───────────────────────────────
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex((ip, port))
        sock.close()
        return result == 0
    
    def is_running(self):
        # ─────────────────────────
        # 17. 현재 실행 여부 조회
        # ─────────────────────────
        result = self._run_vmrun(["list"])
        if result:
            return os.path.normpath(self.vmx_path) in os.path.normpath(result)
        return False
    
    
    @staticmethod
    def collect_resources(ip: str, guest_user: str, pkey_str: str, os_type: str):
        # ──────────────────────────────────────────────────────────
        # 18. CPU/RAM 사용률 수집 (VMX 경로 없이 SSH만으로 동작)
        # ──────────────────────────────────────────────────────────
        def _is_float(value):
            try:
                float(value)
                return True
            except (ValueError, TypeError):
                return False

        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            pkey = paramiko.RSAKey.from_private_key(StringIO(pkey_str))
            client.connect(
                hostname=ip,
                username=guest_user,
                pkey=pkey,
                timeout=10,
                allow_agent=False,
                look_for_keys=False
            )

            # ─── OS 타입별 CPU idle 추출 명령어 ───
            if "ubuntu" in os_type.lower():
                cpu_cmd = (
                    "top -bn1 | grep '%Cpu' | "
                    "awk '{for(i=1;i<=NF;i++) "
                    "if($i==\"id,\" || $i==\"id\") print $(i-1)}' | "
                    "tr -d '%'"
                )
            else:
                # ─── Rocky Linux 9 ───
                cpu_cmd = (
                    "top -bn1 | grep '%Cpu' | "
                    "awk '{print $8}' | tr -d '%,'"
                )

            # ─── RAM 명령어 (공통) ───
            mem_cmd = "free -m | awk 'NR==2{printf \"%.1f\", $3/$2*100}'"

            # ─── CPU 수집 ───
            _, stdout, _ = client.exec_command(cpu_cmd, timeout=10)
            cpu_idle_str = stdout.read().decode().strip()
            cpu_usage    = round(100.0 - float(cpu_idle_str), 1) if _is_float(cpu_idle_str) else 0.0

            # ─── RAM 수집 ───
            _, stdout, _ = client.exec_command(mem_cmd, timeout=10)
            mem_str   = stdout.read().decode().strip()
            mem_usage = float(mem_str) if _is_float(mem_str) else 0.0

            client.close()
            return cpu_usage, mem_usage

        except Exception as e:
            print(f"[모니터링] {ip} 리소스 수집 실패: {e}")
            return None