/**
 * ─────────────────────────────────────
 * 1. 서버 생성 이벤트 리스너 (Create VM)
 * ─────────────────────────────────────
 */
document.getElementById('btnForge').addEventListener('click', async () => {
    const osSelect = document.getElementById('osSelect');
    const osValue = osSelect.value;
    const osText = osSelect.options[osSelect.selectedIndex].text;
    const btn = document.getElementById('btnForge');
    
    // ──────────────────────────────────
    // 1-1. 버튼 비활성화 (중복 클릭 방지)
    // ──────────────────────────────────
    btn.disabled = true;
    btn.innerText = "...";

    try {
        // ────────────────────────────────
        // 1-2. 비동기 생성 요청 (API 호출)
        // ────────────────────────────────
        const response = await fetch('/create-vm', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ os_type: osValue })
        });
        
        if (!response.ok) throw new Error("서버 응답 오류");
        const data = await response.json();
        
        // ──────────────────────────
        // 1-3. UI 업데이트 (목록 갱신)
        // ──────────────────────────
        // 빈 목록 안내 메시지가 있다면 제거
        const emptyMsg = document.getElementById('emptyMsg');
        if (emptyMsg) emptyMsg.remove();

        // 1-4. 신규 VM 아이템 DOM 객체 생성
        const vmItem = document.createElement('div');
        vmItem.className = 'vm-item';

        const infoContainer = document.createElement('div');
        
        const nameSpan = document.createElement('span');
        nameSpan.className = 'vm-name';
        nameSpan.textContent = osText;
        
        const idSpan = document.createElement('span');
        idSpan.className = 'vm-id';
        idSpan.textContent = `ID: ${data.task_id.substring(0, 8)}`;

        const statusBadge = document.createElement('span');
        statusBadge.className = 'status-badge';
        statusBadge.textContent = '준비 중';

        // ──────────────────────────
        // 1-5. 요소 조립 및 화면 삽입
        // ──────────────────────────
        infoContainer.appendChild(nameSpan);
        infoContainer.appendChild(idSpan);
        vmItem.appendChild(infoContainer);
        vmItem.appendChild(statusBadge);

        // 생성된 아이템을 리스트의 가장 처음에 추가
        const vmList = document.getElementById('vmList');
        vmList.insertBefore(vmItem, vmList.firstChild);

    } catch (e) {
        // 에러 발생 시 사용자 알림 및 로그 출력
        alert("서버 연결 실패 또는 오류 발생");
        console.error(e);
    } finally {
        // ─────────────────
        // 1-6. 상태 복구
        // ─────────────────
        btn.disabled = false;
        btn.innerText = "생성";
    }
});