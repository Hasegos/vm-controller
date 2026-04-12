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
 * ─────────────────────────────────────────────────────────────
 * 3. VM 삭제 함수
 * ─────────────────────────────────────────────────────────────
 */
async function deleteVM(vmId, vmName) {
    // ─── 1. 이중 확인 (되돌릴 수 없는 작업) ───
    if (!confirm(`"${vmName}" 서버를 삭제하시겠습니까?\n\n이 작업은 되돌릴 수 없으며, 모든 데이터가 영구적으로 삭제됩니다.`)) {
        return;
    }
    const vmItem = document.querySelector(`.vm-item[data-id="${vmId}"]`);
    const statusBadge = vmItem.querySelector('.status-badge');
    const buttons = vmItem.querySelectorAll('button');

    // ─── 2. UI 즉시 잠금 (삭제 중 상태 표시) ───
    sessionStorage.setItem(`pending_lock_${vmId}`, 'true');
    buttons.forEach(btn => btn.disabled = true);
    statusBadge.textContent = "삭제 중...";
    statusBadge.className = "status-badge bg-danger";

    try {
        // ─── 3. 삭제 API 호출 (DELETE 메서드) ───
        await apiRequest(`/vm/${vmId}`, { method: 'DELETE' });

        // ─── 4. 삭제 완료 후 DOM에서 해당 행 제거 ───
        waitAndRemoveRow(vmId);

    } catch (e) {
        alert("삭제 실패: " + e.message);
        // ─── 5. 실패 시 잠금 해제 및 상태 복구 ───
        sessionStorage.removeItem(`pending_lock_${vmId}`);
        syncStatus();
    }
}

/**
 * ─────────────────────────────────────────────────────────────
 * 4. 삭제 완료 감지 후 DOM row 제거 (Polling 연동)
 *    status-list API에서 해당 vmId가 사라지면 row를 DOM에서 삭제
 * ─────────────────────────────────────────────────────────────
 */
function waitAndRemoveRow(vmId) {
    const intervalId = setInterval(async () => {
        try {
            const data = await apiRequest('/vms/status-list');
            if (!data || !Array.isArray(data)) return;

            // ─── 응답 목록에 해당 VM이 없으면 삭제 완료 ───
            const stillExists = data.some(vm => vm.id === vmId);
            if (!stillExists) {
                clearInterval(intervalId);
                sessionStorage.removeItem(`pending_lock_${vmId}`);

                const row = document.querySelector(`.vm-item[data-id="${vmId}"]`);
                if (row) {
                    // 페이드 아웃 후 DOM 제거
                    row.style.transition = "opacity 0.4s ease";
                    row.style.opacity = "0";
                    setTimeout(() => row.remove(), 400);
                }
            }
        } catch (e) {
            clearInterval(intervalId);
        }
    }, 2000);
}

/**
 * ────────────────────────────────────
 * 5. 서버 상태 실시간 동기화 (Polling)
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
            // [A] DB 기반 상태 체크
            const isDbBusy = ['starting', 'stopping', 'rebooting', 'creating', 'processing', 'deleting'].includes(vm.status);

            // [B] 로컬 스토리지 기반 잠금 체크
            const isLocalLocked = sessionStorage.getItem(`pending_lock_${vm.id}`) === 'true';

            // [C] DB가 'busy' 상태로 전환되면 로컬 잠금 해제
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
        showError(e);
    }
}

/**
 * ─────────────────────────────────────
 * 6. 터미널 새 탭 열기
 * ─────────────────────────────────────
 */
function openTerminal(vmId) {
    window.open(`/terminal/${vmId}`, '_blank');
}

/**
 * ───────────────────────────────
 * 7. 상태 배지 UI 렌더링 유틸리티
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
 * 8. 주기적 실행 설정 (3초 간격 Polling)
 * ─────────────────────────────────────
 */
document.addEventListener('DOMContentLoaded', syncStatus);
setInterval(syncStatus, 3000);