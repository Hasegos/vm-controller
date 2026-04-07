function validateForm() {
    const p1 = document.getElementById('pw1').value;
    const p2 = document.getElementById('pw2').value;
    if (p1 !== p2) {
        alert("비밀번호가 일치하지 않습니다.");
        return false;
    }
    return true;
}