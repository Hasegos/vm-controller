/**
 * ────────────────────────────
 * 1. xterm.js 터미널 초기화
 * ────────────────────────────
 */
const term = new Terminal({
    cursorBlink: true,
    fontSize: 14,
    fontFamily: '"Cascadia Code", "Fira Code", "Courier New", monospace',
    theme: {
        background:  '#0d1117',
        foreground:  '#e6edf3',
        cursor:      '#58a6ff',
        black:       '#0d1117',
        red:         '#f85149',
        green:       '#3fb950',
        yellow:      '#d29922',
        blue:        '#58a6ff',
        magenta:     '#bc8cff',
        cyan:        '#39c5cf',
        white:       '#e6edf3',
        brightBlack: '#6e7681',
    },
    scrollback: 5000,
    allowTransparency: false,
});

const fitAddon = new FitAddon.FitAddon();
term.loadAddon(fitAddon);

// 터미널을 컨테이너에 마운트
term.open(document.getElementById('terminal-container'));
fitAddon.fit();

// 브라우저 창 크기 변경 시 터미널 크기 자동 조정
window.addEventListener('resize', () => fitAddon.fit());

const statusDot   = document.getElementById('connectionStatus');
const statusLabel = document.getElementById('connectionLabel');

/**
 * ─────────────────
 * 2. 상태 UI 유틸
 * ─────────────────
 */
function setStatus(state) {
    const map = {
        connecting:   { label: '연결 중...',  cls: 'connecting' },
        connected:    { label: '연결됨',      cls: 'connected'  },
        disconnected: { label: '연결 끊김',   cls: 'disconnected' },
    };
    const info = map[state] || map.disconnected;
    statusDot.className   = `status-dot ${info.cls}`;
    statusLabel.textContent = info.label;
}

/**
 * ───────────────────────────────
 * 3. 종료 화면 전환 (공통 함수)
 * ───────────────────────────────
 */
function showDisconnectedScreen() {
    clearInterval(statusPollingId);
    setStatus('disconnected');
    document.getElementById('terminal-container').classList.add('hidden');
    document.getElementById('disconnected-screen').classList.remove('hidden');
}

/**
 * ───────────────────────────────
 * 4. WebSocket 연결
 * ───────────────────────────────
 */
const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
const wsUrl    = `${protocol}//${location.host}/ws/terminal/${VM_ID}`;
let   ws       = null;
let   statusPollingId = null;

function connectWS() {
    setStatus('connecting');
    ws = new WebSocket(wsUrl);

    // ─── 4-1. 연결 성공 ───
    ws.onopen = () => {
        setStatus('connected');
        // ─── xterm → WS: 키입력 전송 ───
        term.onData(data => {
            if (ws && ws.readyState === WebSocket.OPEN) {
                ws.send(data);
            }
        });
    };

    // ─── 4-2. 서버 → xterm 출력 ───
    ws.onmessage = (event) => {
        term.write(event.data);
    };

    // ─── 4-3. 연결 종료 ───
    ws.onclose = (event) => {
        if (event.code === 1008) {
            term.writeln('\x1b[31m[CloudForge] 인증 오류로 메인 페이지로 이동합니다.\x1b[0m');
            setTimeout(() => { window.location.href = '/'; }, 2000);
        }

        showDisconnectedScreen();
    };

    ws.onerror = () => {
        setStatus('disconnected');
        term.writeln('\r\n\x1b[31m[CloudForge] WebSocket 오류가 발생했습니다.\x1b[0m');
    };
}

/**
 * ───────────────────────────────
 * 5. VM 상태 폴링 (3초마다)
 * ───────────────────────────────
 */
async function pollVmStatus() {
    try {
        const data = await apiRequest('/vms/status-list');
        if (!data || !Array.isArray(data)) return;

        const vm = data.find(v => v.id === VM_ID);

        // ─── VM이 목록에서 사라졌거나 (삭제됨) running이 아닌 경우 ───
        if (!vm || vm.status !== 'running') {

            if (ws && ws.readyState === WebSocket.OPEN) {
                ws.close();
            }
            showDisconnectedScreen();
        }
    } catch (e) {
        console.warn('[polling] 상태 조회 실패:', e.message);
    }
}

/**
 * ───────────────────────────────
 * 6. 시작
 * ───────────────────────────────
 */
connectWS();
statusPollingId = setInterval(pollVmStatus, 3000);