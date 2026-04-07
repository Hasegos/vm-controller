document.querySelector('form').addEventListener('submit', async function(e) {
    e.preventDefault();
    const alertBox = document.getElementById('errorAlert');
    const formData = new FormData(this);
    
    try {
        const response = await fetch('/login', { 
            method: 'POST', 
            body: formData 
        });
        
        const data = await response.json();

        if (response.ok) {
            // 서버가 준 /dashboard 경로로 이동
            window.location.href = data.redirect_url;
        } else {
            // 401 에러 등의 detail 문구 표시
            alertBox.textContent = data.detail;
            alertBox.style.display = 'block';
        }
    } catch (err) {
        alertBox.textContent = "서버와 통신할 수 없습니다.";
        alertBox.style.display = 'block';
    }
});