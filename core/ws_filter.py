# ───────────────────────────────────
# WebSocket 터미널 위험 명령어 필터링
# ───────────────────────────────────

BLOCK_INPUT_PATTERNS = [

    # ─── 시스템 파괴 ───
    "rm -rf /",
    "rm -rf *",     
    "rm -rf ~",     
    "rm -rf .",     
    ":(){ ",        # Fork Bomb
    "dd if=/dev",
    "mkfs",

    # ─── 시스템 종료/재부팅 ───
    "shutdown",
    "reboot",
    "poweroff",
    ""
    "init 0",
    "init 6",
    "halt",
    "systemctl reboot",
    "systemctl poweroff",
    "systemctl halt",

    # ─── 민감정보 노출 방지 ───
    "cat .env",
    "cat /proc/",
    "printenv",
    " env",         
]

def is_blocked(message: str) -> bool:
    """
    입력 메시지에 위험 패턴이 포함되어 있는지 확인합니다.
    개행 포함 다중 명령어(; && || 구분)도 검사합니다.
    """
    lower = message.lower()

    for pattern in BLOCK_INPUT_PATTERNS:
        if pattern.lower() in lower:
            return True

    # ─── 단독 env 명령어 체크 ───
    stripped = message.strip()
    if stripped == "env" or stripped.startswith("env "):
        return True

    return False