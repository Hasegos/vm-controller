/**
 * ─────────────────────────────────────────────────
 * 1. 클라이언트 측 비밀번호 단순 검증 (validateForm)
 * ─────────────────────────────────────────────────
 */
function validateForm() {
    const p1 = document.getElementById('pw1').value;
    const p2 = document.getElementById('pw2').value;
    const alertBox = document.getElementById('errorAlert');

    // 1-1. 비밀번호 일치 여부 확인
    if (p1 !== p2) {
        alertBox.textContent = "비밀번호가 일치하지 않습니다.";
        alertBox.style.display = 'block';
        alertBox.style.color = '#ff4d4d';
        return false;
    }
    return true;
}

/**
 * ─────────────────────────────────
 * 2. 회원가입 폼 제출 이벤트 리스너
 * ─────────────────────────────────
 */
document.getElementById("registerForm").addEventListener("submit", async function (e) {
    // 2-1. 기본 제출 동작 방지 및 에러 초기화
    e.preventDefault();

    const p1 = document.getElementById("pw1").value;
    const p2 = document.getElementById("pw2").value;

    // 2-2. 최종 제출 전 비밀번호 재확인
    if (p1 !== p2) {
        showError("비밀번호가 일치하지 않습니다.");
        return;
    }

    try {
        // ──────────────────────────
        // 2-3. 회원가입 API 요청 실행
        // ──────────────────────────
        // FormData(this)를 통해 폼에 입력된 username, password 등을 전송합니다.
        const data = await apiRequest("/register", {
            method: "POST",
            body: new FormData(this),
        });

        // ──────────────────────────
        // 2-4. 가입 완료 및 리다이렉트
        // ──────────────────────────
        alert("회원가입이 완료되었습니다.");
        window.location.href = data.redirect_url;
    } catch (err) {
        // ──────────────────────────
        // 2-5. 서버 에러 발생 시 처리
        // ──────────────────────────
        // 중복 계정 존재 또는 비밀번호 정책 미달 등의 에러 메시지를 표시합니다.
        showError(err.message);
    }
});