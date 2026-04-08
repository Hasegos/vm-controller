/**
 * ─────────────────────────────── 
 * 1. 로그인 폼 제출 이벤트 리스너
 * ─────────────────────────────── 
 */
document.querySelector("form").addEventListener("submit", async function (e) {
    e.preventDefault();
    showError(""); 

    try {
        // ──────────────────────────
        // 1-2. 로그인 API 요청 실행
        // ──────────────────────────
        // FormData(this)를 통해 폼 내부의 username, password 데이터를 자동으로 수집합니다.
        const data = await apiRequest("/login", {
            method: "POST",
            body: new FormData(this),
        });

        // ──────────────────────────
        // 1-3. 인증 성공 시 페이지 이동
        // ──────────────────────────
        // 서버에서 전달받은 redirect_url
        if (data && data.redirect_url) {
            window.location.href = data.redirect_url;
        }
    } catch (err) {
        // ──────────────────────────
        // 1-4. 예외 발생 시 처리
        // ──────────────────────────
        // 유효성 검사 실패 또는 인증 오류 메시지를 화면에 표시합니다.
        showError(err.message);
    }
});