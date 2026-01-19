function updateTime() {
    const timeElement = document.getElementById('current-time');
    if (!timeElement) return;

    const now = new Date();
    const hours = now.getHours();
    const minutes = now.getMinutes();
    const ampm = hours >= 12 ? 'PM' : 'AM';
    const displayHours = hours % 12 || 12;
    const displayMinutes = minutes.toString().padStart(2, '0');

    timeElement.textContent = `${displayHours}:${displayMinutes} ${ampm}`;
}

updateTime();
setInterval(updateTime, 60000);
