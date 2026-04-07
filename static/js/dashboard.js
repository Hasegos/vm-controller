document.getElementById('btnForge').addEventListener('click', async () => {
    const osSelect = document.getElementById('osSelect');
    const osValue = osSelect.value;
    const osText = osSelect.options[osSelect.selectedIndex].text;
    const btn = document.getElementById('btnForge');
    
    btn.disabled = true;
    btn.innerText = "...";

    try {
        const response = await fetch('/create-vm', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ os_type: osValue })
        });
        
        if (!response.ok) throw new Error("서버 응답 오류");
        const data = await response.json();
        
        // 1. 빈 목록 메시지 제거
        const emptyMsg = document.getElementById('emptyMsg');
        if (emptyMsg) emptyMsg.remove();

        // 2. DOM 객체 생성 (innerHTML 미사용)
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

        // 3. 구조 조립
        infoContainer.appendChild(nameSpan);
        infoContainer.appendChild(idSpan);
        vmItem.appendChild(infoContainer);
        vmItem.appendChild(statusBadge);

        // 4. 목록 최상단에 추가
        const vmList = document.getElementById('vmList');
        vmList.insertBefore(vmItem, vmList.firstChild);

    } catch (e) {
        alert("서버 연결 실패 또는 오류 발생");
        console.error(e);
    } finally {
        btn.disabled = false;
        btn.innerText = "생성";
    }
});