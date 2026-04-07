function validateForm() {
    const p1 = document.getElementById('pw1').value;
    const p2 = document.getElementById('pw2').value;
    const alertBox = document.getElementById('errorAlert');

    if (p1 !== p2) {
        alertBox.textContent = "비밀번호가 일치하지 않습니다.";
        alertBox.style.display = 'block';
        alertBox.style.color = '#ff4d4d'; // 에러 강조
        return false;
    }
    return true;
}

document.getElementById('registerForm').addEventListener('submit', async function(e) {
    e.preventDefault();
    const alertBox = document.getElementById('errorAlert');
    const formData = new FormData(this);

    try {
        const response = await fetch('/register', {
            method: 'POST',
            body: formData
        });

        const data = await response.json();

        if (response.ok) {
            // 서버가 준 /login 경로로 이동
            window.location.href = data.redirect_url;
        } else {
            // detail 문자열을 바로 표시
            alertBox.textContent = data.detail;
            alertBox.style.display = 'block';
        }
    } catch (err) {
        alertBox.textContent = "서버 연결에 실패했습니다.";
        alertBox.style.display = 'block';
    }
});