import redis

from core.config import settings
from collections import defaultdict

# ─────────────────────────────────
# Redis 기반 WebSocket 연결 수 관리
# ─────────────────────────────────
redis_client = redis.Redis(host="localhost", port=6379, db=1, decode_responses=True)

# ──────────────────────────────────────────────────────────────────
# 유저별 WS 연결 시도 타임스탬프 목록
# Rate Limit 용도이므로 프로세스 메모리로 충분 (재시작 시 초기화 허용)
# ──────────────────────────────────────────────────────────────────
connection_attempts: dict[str, list] = defaultdict(list)

def _redis_conn_key(vm_id: int) -> str:
    return f"ws_conn:{vm_id}"

def get_active_connections(vm_id: int) -> int:
    """
    특정 VM의 현재 활성 WebSocket 연결 수를 반환합니다.
    """
    val = redis_client.get(_redis_conn_key(vm_id))
    return int(val) if val else 0

def incr_connection(vm_id: int):
    """
    VM 연결 수를 1 증가시키고 TTL을 갱신합니다.
    WebSocket 수락 직후 호출합니다.
    """
    key = _redis_conn_key(vm_id)
    redis_client.incr(key)
    redis_client.expire(key, settings.WS_CONN_TTL)

def decr_connection(vm_id: int):
    """
    VM 연결 수를 1 감소시킵니다. (최솟값 0 보장)
    WebSocket finally 블록에서 반드시 호출합니다.
    """
    key = _redis_conn_key(vm_id)
    current = get_active_connections(vm_id)
    if current > 0:
        redis_client.decr(key)