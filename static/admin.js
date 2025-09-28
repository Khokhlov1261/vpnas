// ==============================
// 📊 Форматирование данных
// ==============================
function formatBytes(bytes) {
    return (bytes / 1024 / 1024).toFixed(2) + " MB";
}

function formatSpeed(bytesPerSec) {
    return (bytesPerSec / 1024).toFixed(2) + " KB/s";
}

function formatLastSeen(timestamp, online) {
    if (online) return "сейчас"; // клиент онлайн
    if (!timestamp || timestamp === 0) return "-";

    const now = Date.now();
    const delta = Math.floor((now / 1000) - timestamp);

    if (delta < 60) return "менее минуты назад";
    if (delta < 3600) return `${Math.floor(delta / 60)} мин. назад`;
    if (delta < 86400) return `${Math.floor(delta / 3600)} ч. назад`;

    // более суток назад — показываем дату и время
    const date = new Date(timestamp * 1000);
    const day = String(date.getDate()).padStart(2, "0");
    const month = String(date.getMonth() + 1).padStart(2, "0");
    const hours = String(date.getHours()).padStart(2, "0");
    const minutes = String(date.getMinutes()).padStart(2, "0");
    return `${day}.${month} ${hours}:${minutes}`;
}

// ==============================
// 🔄 Обновление статистики
// ==============================
function updateStats() {
    fetch("/admin/stats")
        .then(resp => resp.json())
        .then(data => {
            // системные метрики
            document.getElementById("cpu").innerText = data.cpu_percent;
            document.getElementById("ram").innerText = data.ram_percent;
            document.getElementById("disk").innerText = data.disk_percent;

            const tbody = document.querySelector("#traffic-table tbody");
            tbody.innerHTML = "";

            data.clients.forEach(c => {
                const tr = document.createElement("tr");
                tr.id = `client-${c.public_key}`;

                // генерируем строки, добавляем моргание только на email
                tr.innerHTML = `
                    <td data-label="Email" class="${c.online ? 'email-online' : ''}">${c.email}</td>
                    <td data-label="Plan">${c.plan}</td>
                    <td data-label="Client IP">${c.client_ip}</td>
                    <td data-label="Public Key">${c.public_key}</td>
                    <td data-label="RX">${formatBytes(c.rx_bytes)}</td>
                    <td data-label="TX">${formatBytes(c.tx_bytes)}</td>
                    <td class="${c.online ? 'online' : 'offline'}" data-label="Online">${c.online ? 'Да' : 'Нет'}</td>
                    <td data-label="Last seen">${formatLastSeen(c.last_seen || c.start_date, c.online)}</td>
                    <td data-label="Start">${c.start_date || '-'}</td>
                    <td data-label="End">${c.end_date || '-'}</td>
                    <td data-label="Action"><button class="delete-btn" data-key="${c.public_key}">Удалить</button></td>
                `;
                tbody.appendChild(tr);
            });

            // обработчики кнопок удаления
            document.querySelectorAll(".delete-btn").forEach(button => {
                button.onclick = () => {
                    const publicKey = button.dataset.key;
                    if (!confirm("Удалить этого клиента?")) return;
                    fetch(`/admin/delete/${encodeURIComponent(publicKey)}`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        credentials: 'include'
                    })
                    .then(response => {
                        if (response.ok) {
                            const row = document.getElementById(`client-${publicKey}`);
                            if (row) row.remove();
                        } else {
                            alert("Ошибка при удалении клиента");
                        }
                    })
                    .catch(err => {
                        console.error(err);
                        alert("Ошибка при удалении клиента");
                    });
                };
            });
        })
        .catch(err => console.error(err));
}

// ==============================
// 🔁 Автообновление каждые 5 секунд
// ==============================
setInterval(updateStats, 5000);
updateStats(); // первый вызов сразу