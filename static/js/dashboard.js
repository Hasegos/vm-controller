/**
 * ─────────────────────────────────────────────────────────────
 * 1. 서버 생성 이벤트 (인프라 신규 Forge)
 * ─────────────────────────────────────────────────────────────
 */
document.getElementById('btnForge').addEventListener('click', async () => {
    const osSelect = document.getElementById('osSelect');
    const osValue = osSelect.value;
    const btn = document.getElementById('btnForge');
    
    // ─── 1. 버튼 UI 비활성화 (중복 클릭 방지) ───
    btn.disabled = true;
    const originalText = btn.innerText;
    btn.innerText = "요청 중...";

    try {
        // ─── 2. 생성 API 호출 ───
        await apiRequest('/create-vm', {
            method: 'POST',
            body: JSON.stringify({ os_type: osValue })
        });
        
        alert("인프라 생성이 시작되었습니다. 목록에서 상태를 확인하세요.");

        // ─── 3. 즉시 상태 동기화 ───
        await syncStatus(); 

    } catch (e) {
        alert("생성 실패: " + e.message);
    } finally {
        // ─── 4. UI 복구 ───
        btn.disabled = false;
        btn.innerText = originalText;
    }
});

/**
 * ────────────────────────────────────────
 * 2. 전원 제어 함수 (Start, Stop, Reboot)
 * ────────────────────────────────────────
 */
async function controlVM(vmId, action) {
    const vmItem = document.querySelector(`.vm-item[data-id="${vmId}"]`);
    const statusBadge = vmItem.querySelector('.status-badge');
    const buttons = vmItem.querySelectorAll('button');

    // ─── 1. 위험 액션 컨펌 ───
    if (action === 'stop_hard' && !confirm("강제 종료하시겠습니까? 데이터 손실 위험이 있습니다.")) {
        return;
    }

    // ─── 2. 로컬 잠금 설정 (Race Condition 방지) ───
    sessionStorage.setItem(`pending_lock_${vmId}`, 'true');

    // ─── 3. UI 즉시 잠금 반영 ───
    buttons.forEach(btn => btn.disabled = true);
    statusBadge.textContent = "처리 중...";
    statusBadge.className = "status-badge processing bg-primary";

    try {
        // ─── 4. 제어 API 호출 ───
        await apiRequest(
            `/vm/${vmId}/control?action=${action}`,
            { method: 'POST' }
        );        
        await syncStatus();
        
    } catch (e) {
        alert(e.message);
        // ─── 5. 에러 시 잠금 해제 및 복구 ───
        sessionStorage.removeItem(`pending_lock_${vmId}`);
        syncStatus();
    }
}

/**
 * ────────────────────────────────────
 * 3. 서버 상태 실시간 동기화 (Polling)
 * ────────────────────────────────────
 */
async function syncStatus() {
    try {
        // ─── 1. 최신 상태 목록 조회 ───
        const data = await apiRequest('/vms/status-list');
        if (!data || !Array.isArray(data)) return;

        data.forEach(vm => {
            const row = document.querySelector(`.vm-item[data-id="${vm.id}"]`);
            if (!row) return;

            const badge = row.querySelector('.status-badge');
            const btns = row.querySelectorAll('.control-btn');

            // ─── 2. 잠금 조건 계산 ───
            // [A] DB 기반 상태 체크 (작업 중 여부)
            const isDbBusy = ['starting', 'stopping', 'rebooting', 'creating', 'processing'].includes(vm.status);
            
            // [B] 로컬 스토리지 기반 잠금 체크 (API 응답 전 찰나의 시간 대비)
            const isLocalLocked = sessionStorage.getItem(`pending_lock_${vm.id}`) === 'true';

            // [C] 잠금 해제: DB 상태가 '작업 중'으로 전환되었다면 로컬 잠금 해제
            if (isDbBusy && isLocalLocked) {
                sessionStorage.removeItem(`pending_lock_${vm.id}`);
            }

            // [D] 최종 UI 잠금 여부 결정
            const finalLock = isDbBusy || isLocalLocked;
            
            // ─── 3. UI 업데이트 ───
            updateBadgeUI(badge, vm.status);
            btns.forEach(btn => {
                btn.disabled = finalLock;
            });
        });
    } catch (e) { 
        showError(e)
    }
}

/**
 * ───────────────────────────────
 * 4. 상태 배지 UI 렌더링 유틸리티
 * ───────────────────────────────
 */
function updateBadgeUI(badge, status) {
    const statusMap = {
        'running': { text: '구동 중', class: 'bg-success' },
        'stopped': { text: '정지됨', class: 'bg-secondary' },
        'starting': { text: '부팅 중...', class: 'bg-warning' },
        'stopping': { text: '종료 중...', class: 'bg-warning' },
        'rebooting': { text: '재부팅 중...', class: 'bg-warning' },
        'creating': { text: '생성 중...', class: 'bg-info' },
        'error': { text: '오류', class: 'bg-danger' }
    };
    const info = statusMap[status] || { text: status, class: 'bg-dark' };
    
    if (badge.textContent !== info.text) {
        badge.textContent = info.text;
        badge.className = `status-badge ${info.class}`;
    }
}

/**
 * ─────────────────────────────────────
 * 5. 주기적 실행 설정 (3초 간격 Polling)
 * ─────────────────────────────────────
 */
document.addEventListener('DOMContentLoaded', syncStatus);
setInterval(syncStatus, 3000);