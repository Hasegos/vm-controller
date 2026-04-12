import time
import asyncio
import asyncssh

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Request, HTTPException
from sqlalchemy.orm import Session
from db.session import get_db

from core.auth import get_current_user
from core.config import settings
from core.security import decode_access_token
from core.crypto_utils import decrypt_private_key
from core.templates import templates
from core.ws_manager import(
    get_active_connections,
    incr_connection,
    decr_connection,
    connection_attempts
)
from core.ws_filter import is_blocked

from models.vm_model import VM
from models.user_model import User

router = APIRouter()

# ───────────────────────
# 1. 터미널 페이지 렌더링 
# ───────────────────────
@router.get("/terminal/{vm_id}")
async def terminal_page(
    vm_id: int,
    request: Request,
    db: Session = Depends(get_db),
    username: str = Depends(get_current_user)
):
    # ─── 1. 사용자 조회 ───
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")

    # ─── 2. VM 소유권 확인 ───
    vm = db.query(VM).filter(VM.id == vm_id, VM.owner_id == user.id).first()
    if not vm:
        raise HTTPException(status_code=403, detail="접근 권한이 없습니다.")

    # ─── 3. VM 실행 상태 확인 ───
    if vm.status != "running":
        raise HTTPException(status_code=400, detail="실행 중인 서버에만 접속할 수 있습니다.")

    return templates.TemplateResponse(
        request=request,
        name="terminal.html",
        context={
            "request": request,
            "vm_id": vm_id,
            "ip_address": vm.ip_address,
            "vm_name": vm.vm_name,
        }
    )

# ───────────────────────────────
# 2. WebSocket 터미널 엔드포인트 
# ───────────────────────────────
@router.websocket("/ws/terminal/{vm_id}")
async def terminal_ws(
    websocket: WebSocket,
    vm_id: int,
    db: Session = Depends(get_db)
):
    # ───────────────────────────────
    # 보안 체크 1: Rate Limiting
    # ───────────────────────────────
    try:
        username = await get_current_user(websocket)
    except HTTPException:
        await websocket.close(code=1008)
        return

    now = time.time()

    # ─── 시간 윈도우 밖 항목 제거 후 횟수 체크 ───
    connection_attempts[username] = [
        t for t in connection_attempts[username]
        if now - t < settings.RATE_LIMIT_WINDOW_SEC
    ]

    if len(connection_attempts[username]) >= settings.RATE_LIMIT_MAX_ATTEMPTS:
        await websocket.accept()
        await websocket.send_text(
            "\r\n\033[31m[보안] 연결 시도가 너무 많습니다. 잠시 후 다시 시도하세요.\033[0m\r\n"
        )
        await websocket.close(code=1008)
        return

    connection_attempts[username].append(now)

    # ───────────────────────────────
    # 보안 체크 2: 인증 및 소유권 확인
    # ───────────────────────────────
    user = db.query(User).filter(User.username == username).first()
    if not user:
        await websocket.close(code=1008)
        return

    vm = db.query(VM).filter(VM.id == vm_id, VM.owner_id == user.id).first()
    if not vm:
        await websocket.accept()
        await websocket.send_text("\r\n\033[31m[오류] 접근 권한이 없습니다.\033[0m\r\n")
        await websocket.close(code=1008)
        return

    if vm.status != "running":
        await websocket.accept()
        await websocket.send_text("\r\n\033[31m[오류] 서버가 실행 중이 아닙니다.\033[0m\r\n")
        await websocket.close(code=1008)
        return

    # ──────────────────────────────────
    # 보안 체크 3: VM당 동시 연결 수 제한
    # ──────────────────────────────────
    if get_active_connections(vm_id) >= settings.MAX_CONNECTIONS_PER_VM:
        await websocket.accept()
        await websocket.send_text(
            f"\r\n\033[31m[보안] VM당 최대 {settings.MAX_CONNECTIONS_PER_VM}개 연결만 허용됩니다.\033[0m\r\n"
        )
        await websocket.close(code=1008)
        return

    # ─── WebSocket 수락 및 연결 수 등록 ───
    await websocket.accept()
    incr_connection(vm_id)
    print(f"[WS] 연결 수락: VM {vm_id} | 현재 연결 수: {get_active_connections(vm_id)}")

    # ────────────────────────────────
    # 토큰 재검증 초기값 설정
    # JWT 만료 30분 → 25분마다 재검증 
    # ────────────────────────────────
    TOKEN_RECHECK_SEC = 25 * 60
    last_token_check  = time.time()

    ssh_conn    = None
    ssh_process = None

    try:
        # ────────────────────────────
        # known_hosts fingerprint 검증
        # ────────────────────────────
        known_hosts_param = None
        if vm.ssh_host_fingerprint:
            try:
                known_hosts_param = asyncssh.import_known_hosts(
                    f"{vm.ssh_host_fingerprint}\n"
                )
                print(f"fingerprint 검증 활성화: {vm.ssh_host_fingerprint}")
            except Exception as e:
                print(f"[WARN] fingerprint 파싱 실패, 검증 생략: {e}")

        # ────────────────────────────────
        # SSH 연결 (asyncssh PTY 채널)
        # ────────────────────────────────
        connect_kwargs  = dict(
            host=vm.ip_address,
            username=settings.GUEST_USER,
            known_hosts=known_hosts_param,
            connect_timeout=10
        )

        if vm.ssh_private_key:
            try:
                # DB에서 암호화된 개인키 복호화
                private_key_str = decrypt_private_key(vm.ssh_private_key)
                private_key_obj = asyncssh.import_private_key(private_key_str)
                connect_kwargs["client_keys"] = [private_key_obj]
                connect_kwargs["known_hosts"] = known_hosts_param
                print(f"PEM 키 기반 SSH 접속: VM {vm_id}")

            except Exception as e:
                print(f"[WARN] 개인키 복호화 실패, 패스워드 fallback: {e}")
                connect_kwargs["password"] = settings.GUEST_PW

        else:
            # 레거시 VM (개인키 없음) → 패스워드 방식
            connect_kwargs["password"] = settings.GUEST_PW
            print(f"[INFO] 패스워드 방식 SSH 접속 (레거시 VM): VM {vm_id}")

        try:
            ssh_conn = await asyncssh.connect(**connect_kwargs)
            # ─── PTY(Pseudo Terminal) ───
            ssh_process = await ssh_conn.create_process(
                "bash",
                term_type="xterm-256color",
                request_pty=True
            )

        except (asyncssh.Error, OSError) as e:
            print(f"[SSH 연결 실패] {str(e)}")
            await websocket.send_text(
                f"\r\n\033[31m[오류] SSH 연결 실패: {str(e)}\033[0m\r\n"
            )
            await websocket.close(code=1011)
            return

        await websocket.send_text("\r\n\033[32m[CloudForge] 터미널에 연결되었습니다.\033[0m\r\n")

        # ────────────────────────────────
        # 양방향 브릿지 (WS ↔ SSH)
        # ────────────────────────────────
        async def ws_to_ssh():
            """클라이언트 키입력 → SSH stdin"""

            nonlocal last_token_check
            cmd_buffer = ""

            while True:
                try:
                    # ─── idle timeout ───
                    message = await asyncio.wait_for(
                        websocket.receive_text(),
                        timeout=settings.IDLE_TIMEOUT
                    )

                    # ─── 메시지 크기 제한 ───
                    if len(message.encode("utf-8")) > settings.MAX_MESSAGE_BYTES:
                        print(f"[보안] 메시지 크기 초과 무시: {len(message)} bytes")
                        continue
                    
                    # ─── 버퍼에 누적 ───
                    if message == "\x7f":
                        cmd_buffer = cmd_buffer[:-1]
                    elif "\r" in message or "\n" in message:
                    # ─── 위험 명령어 필터링 ───
                        if is_blocked(cmd_buffer.strip()):
                            await websocket.send_text(
                                "\r\n\033[31m[CloudForge] 허용되지 않은 명령입니다.\033[0m\r\n"
                            )
                            print(f"차단: {repr(cmd_buffer.strip())}")
                            cmd_buffer = ""
                            continue
                        cmd_buffer = ""
                    else:
                        cmd_buffer += message

                    # ─── 25분마다 토큰 재검증 ───
                    now = time.time()
                    if now - last_token_check >= TOKEN_RECHECK_SEC:
                        token = websocket.cookies.get("access_token", "")

                        if token.startswith("Bearer "):
                            token = token[7:]
                        payload = decode_access_token(token)

                        if payload in ("expired", "invalid") or not payload:
                            await websocket.send_text(
                                "\r\n\033[31m[CloudForge] 세션이 만료되었습니다. 다시 로그인하세요.\033[0m\r\n"
                            )
                            print(f"토큰 만료 → 세션 강제 종료: {username}")
                            break
                        last_token_check = now

                    ssh_process.stdin.write(message)
                
                except asyncio.TimeoutError:
                    await websocket.send_text(
                        "\r\n\033[31m[CloudForge] 15분 동안 입력이 없어 연결이 종료됩니다.\033[0m\r\n"
                    )
                    print(f"[P1-2] idle timeout: VM {vm_id}, user {username}")
                    break

                except WebSocketDisconnect:
                    break
                except Exception:
                    break

        async def ssh_to_ws():
            """SSH stdout → 클라이언트 xterm 출력"""
            while True:
                try:
                    output = await ssh_process.stdout.read(4096)
                    if not output:
                        # ─── SSH 연결 종료 (VM 꺼짐 등) ───
                        await websocket.send_text(
                            "\r\n\033[33m[CloudForge] 서버와의 연결이 종료되었습니다.\033[0m\r\n"
                        )
                        break
                    await websocket.send_text(output)
                except Exception:
                    break

        # ─── 두 코루틴 동시 실행 — 하나라도 종료되면 전체 종료 ───
        await asyncio.gather(ws_to_ssh(), ssh_to_ws())

    except WebSocketDisconnect:
        print(f"[WS] 클라이언트 연결 종료: VM {vm_id}")

    except Exception as e:
        print(f"[WS] 예외 발생: {str(e)}")
        try:
            await websocket.send_text(
                f"\r\n\033[31m[오류] 연결이 종료되었습니다: {str(e)}\033[0m\r\n"
            )
        except Exception:
            pass

    finally:
        # ─── 연결 종료 정리 ───
        if ssh_process:
            ssh_process.close()
        if ssh_conn:
            ssh_conn.close()

        decr_connection(vm_id)
        print(f"[WS] 연결 해제: VM {vm_id} | 남은 연결 수: {get_active_connections(vm_id)}")