
window.addEventListener('DOMContentLoaded', () => {
    const statusEl = document.getElementById('status');
    const downloadLink = document.getElementById('downloadLink');
    const qrContainer = document.getElementById('qrContainer');
    const app = document.getElementById('app');

    if (!app) {
        console.error("Не найден элемент #app");
        return;
    }


    const configText = JSON.parse(app.dataset.config);
    const planName = JSON.parse(app.dataset.plan);

    if (!configText || !planName) {
        console.error("Нет данных конфигурации или плана");
        statusEl.textContent = "Ошибка загрузки конфигурации";
        return;
    }


    const blob = new Blob([configText], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    downloadLink.href = url;
    downloadLink.download = `securelink_${planName.replace(/\s/g, '')}.conf`;
    downloadLink.textContent = `Скачать конфиг (${planName})`;


    QRCode.toCanvas(configText, { width: 200 }, (err, canvas) => {
        if (err) {
            console.error("Ошибка генерации QR:", err);
        } else {
            qrContainer.appendChild(canvas);
        }
    });

    statusEl.textContent = 'Конфигурация готова!';
});