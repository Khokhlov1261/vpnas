/**
 * Dashboard SPA для SecureLink
 */

class DashboardApp {
    constructor() {
        this.currentUser = null;
        this.authToken = null;
        this.telegramWebApp = null;
        this.currentSection = 'dashboard';
        document.addEventListener('DOMContentLoaded', () => this.init());
    }

    async init() {
        try {
            this.initTelegramWebApp();
            await this.checkAuth();
            this.initUI();
            await this.showSection(this.currentSection);
        } catch (err) {
            console.error('Ошибка инициализации:', err);
            this.showToast('Ошибка загрузки приложения', 'error');
        }
    }

    initTelegramWebApp() {
        if (window.Telegram?.WebApp) {
            this.telegramWebApp = window.Telegram.WebApp;
            this.telegramWebApp.ready();
            this.telegramWebApp.expand();

            if (this.telegramWebApp.colorScheme === 'dark') {
                document.body.classList.add('telegram-dark');
            }

            this.telegramWebApp.MainButton.setText('🚀 Открыть VPN');
            this.telegramWebApp.MainButton.show();
            this.telegramWebApp.MainButton.onClick(() => window.location.href = '/');

            console.log('Telegram WebApp ready:', this.telegramWebApp.initDataUnsafe);
        }
    }

    async checkAuth() {
        this.authToken = localStorage.getItem('authToken');
        if (this.authToken) {
            try {
                const data = await this.apiCall('/auth/me');
                this.currentUser = data.user;
                return;
            } catch (err) {
                console.warn('Auth token invalid, removing:', err);
                localStorage.removeItem('authToken');
            }
        }

        if (this.telegramWebApp?.initData) {
            await this.authenticateWithTelegram();
        } else {
            console.warn('Нет токена и Telegram initData — редирект на /');
            window.location.href = '/';
        }
    }

    async authenticateWithTelegram() {
        try {
            const res = await fetch('/auth/telegram', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ init_data: this.telegramWebApp.initData })
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.error || 'Ошибка авторизации');
            this.authToken = data.token;
            this.currentUser = data.user;
            localStorage.setItem('authToken', this.authToken);
            this.showToast('Успешная авторизация!', 'success');
        } catch (err) {
            console.error('Ошибка Telegram auth:', err);
            this.showToast('Ошибка авторизации', 'error');
            window.location.href = '/';
        }
    }

    initUI() {
        // Навигация
        document.querySelectorAll('.nav-link').forEach(link => {
            link.addEventListener('click', async e => {
                e.preventDefault();
                const section = link.dataset.section;
                await this.showSection(section);
            });
        });

        // Кнопки
        document.getElementById('logoutBtn')?.addEventListener('click', () => this.logout());
        document.getElementById('renewSubscriptionBtn')?.addEventListener('click', () => window.location.href = '/');
        document.getElementById('buyNewSubscriptionBtn')?.addEventListener('click', () => window.location.href = '/');
        document.getElementById('saveSettingsBtn')?.addEventListener('click', () => this.saveSettings());
        document.getElementById('markAllReadBtn')?.addEventListener('click', () => this.markAllNotificationsRead());

        // Модалки
        document.getElementById('configModalClose')?.addEventListener('click', () => this.closeModal('configModal'));
        document.getElementById('configModal')?.addEventListener('click', e => {
            if (e.target.id === 'configModal') this.closeModal('configModal');
        });

        this.updateUserInfo();
    }

    updateUserInfo() {
        if (!this.currentUser) return;
        const avatar = document.getElementById('avatarPlaceholder');
        if (avatar) avatar.textContent = (this.currentUser.first_name?.[0] || 'U').toUpperCase();
        const username = document.getElementById('username');
        if (username) username.textContent = `@${this.currentUser.username || 'user'}`;
    }

    async showSection(sectionName) {
        this.currentSection = sectionName;
        document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));
        document.querySelector(`[data-section="${sectionName}"]`)?.classList.add('active');
        document.querySelectorAll('.content-section').forEach(s => s.classList.remove('active'));
        document.getElementById(`${sectionName}Section`)?.classList.add('active');

        switch (sectionName) {
            case 'dashboard': await this.loadDashboardData(); break;
            case 'subscriptions': await this.loadSubscriptions(); break;
            case 'configs': await this.loadConfigs(); break;
            case 'traffic': await this.loadTrafficStats(); break;
            case 'notifications': await this.loadNotifications(); break;
            case 'settings': await this.loadSettings(); break;
        }
    }

    async loadDashboardData() {
        try {
            const subs = await this.safeApiCall('/api/user/subscriptions');
            this.updateDashboardSubscriptions(subs?.subscriptions || []);
            const traffic = await this.safeApiCall('/api/user/traffic');
            this.updateDashboardTraffic(traffic || {});
        } catch (err) { console.error('Ошибка dashboard data:', err); }
    }

    async loadSubscriptions() {
        const container = document.getElementById('subscriptionsList');
        if (!container) return;
        container.innerHTML = '<div class="loading">Загрузка подписок...</div>';
        try {
            const data = await this.safeApiCall('/api/user/subscriptions');
            this.renderSubscriptions(data?.subscriptions || []);
        } catch (err) {
            console.error('Ошибка подписок:', err);
            container.innerHTML = '<div class="error">Ошибка загрузки подписок</div>';
        }
    }

    async loadConfigs() {
        const container = document.getElementById('configsList');
        if (!container) return;
        container.innerHTML = '<div class="loading">Загрузка конфигураций...</div>';
        try {
            const data = await this.safeApiCall('/api/user/configs');
            this.renderConfigs(data?.configs || []);
        } catch (err) {
            console.error('Ошибка конфигураций:', err);
            container.innerHTML = '<div class="error">Ошибка загрузки конфигураций</div>';
        }
    }

    async loadTrafficStats() {
        const container = document.getElementById('trafficStats');
        if (!container) return;
        container.innerHTML = '<div class="loading">Загрузка статистики...</div>';
        try {
            const data = await this.safeApiCall('/api/user/traffic');
            this.renderTrafficStats(data || {});
        } catch (err) {
            console.error('Ошибка трафика:', err);
            container.innerHTML = '<div class="error">Ошибка загрузки статистики</div>';
        }
    }

    async loadNotifications() {
        const container = document.getElementById('notificationsList');
        if (!container) return;
        container.innerHTML = '<div class="loading">Загрузка уведомлений...</div>';
        try {
            const data = await this.safeApiCall('/api/user/notifications');
            this.renderNotifications(data?.notifications || []);
            this.updateNotificationBadge(data?.unread_count || 0);
        } catch (err) {
            console.error('Ошибка уведомлений:', err);
            container.innerHTML = '<div class="error">Ошибка загрузки уведомлений</div>';
        }
    }

    async loadSettings() {
        if (!this.currentUser) return;
        document.getElementById('usernameInput')?.value = this.currentUser.username || '';
        document.getElementById('emailInput')?.value = this.currentUser.email || '';
        document.getElementById('languageSelect')?.value = this.currentUser.language_code || 'ru';
    }

    async downloadConfig(configId) {
        try {
            const res = await fetch(`/api/configs/${configId}/download`, {
                headers: { 'Authorization': `Bearer ${this.authToken}` }
            });
            if (!res.ok) throw new Error('Ошибка скачивания');

            const blob = await res.blob();
            const a = document.createElement('a');
            a.href = URL.createObjectURL(blob);
            a.download = `securelink_${configId}.conf`;
            document.body.appendChild(a);
            a.click();
            a.remove();
            this.showToast('Конфигурация скачана', 'success');
        } catch (err) {
            console.error('downloadConfig error', err);
            this.showToast('Ошибка скачивания', 'error');
        }
    }

    async showQRCode(configId) {
        try {
            const data = await this.safeApiCall(`/api/configs/${configId}/qr`);
            if (data?.qr_url) {
                const img = document.getElementById('qrImage');
                if (img) img.src = data.qr_url;
                this.showModal('configModal');
            } else {
                this.showToast('QR-код недоступен', 'error');
            }
        } catch (err) {
            console.error('showQRCode error', err);
            this.showToast('Ошибка загрузки QR', 'error');
        }
    }

    async logout() {
        try {
            if (this.authToken) await this.safeApiCall('/auth/logout', 'POST');
        } catch (err) {
            console.error('Logout error', err);
        } finally {
            localStorage.removeItem('authToken');
            this.authToken = null;
            this.currentUser = null;
            window.location.href = '/';
        }
    }

    // -------------------------
    // Общие утилиты
    // -------------------------
    async apiCall(endpoint, method = 'GET', body = null) {
        const options = { method, headers: { 'Content-Type': 'application/json' } };
        if (this.authToken) options.headers['Authorization'] = `Bearer ${this.authToken}`;
        if (body) options.body = JSON.stringify(body);

        const res = await fetch(endpoint, options);
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Ошибка API');
        return data;
    }

    // Безопасная версия для try/catch
    async safeApiCall(endpoint, method = 'GET', body = null) {
        try { return await this.apiCall(endpoint, method, body); }
        catch (err) { console.error(`API call error (${endpoint}):`, err); return null; }
    }

    showModal(id) { document.getElementById(id)?.classList.add('active'); }
    closeModal(id) { document.getElementById(id)?.classList.remove('active'); }

    showToast(msg, type = 'info') {
        const container = document.getElementById('toastContainer');
        if (!container) return;
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.textContent = msg;
        container.appendChild(toast);
        setTimeout(() => toast.remove(), 5000);
    }

    updateNotificationBadge(count) {
        const badge = document.getElementById('notificationBadge');
        if (!badge) return;
        badge.textContent = count > 0 ? count : '';
        badge.style.display = count > 0 ? 'inline-block' : 'none';
    }

    formatBytes(bytes) {
        if (!bytes) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return `${(bytes / Math.pow(k, i)).toFixed(2)} ${sizes[i]}`;
    }

    formatSpeed(bps) { return this.formatBytes(bps) + '/s'; }
    formatDate(ds) { return ds ? new Date(ds).toLocaleString('ru-RU', { hour12: false }) : '—'; }
    isExpired(expiresAt) { return expiresAt ? new Date(expiresAt) < new Date() : false; }
    getStatusClass(status, expiresAt) { if (this.isExpired(expiresAt)) return 'expired'; return status === 'paid' ? 'active' : status === 'pending' ? 'pending' : 'expired'; }
    getStatusText(status, expiresAt) { return this.isExpired(expiresAt) ? 'Истекла' : status === 'paid' ? 'Активна' : status === 'pending' ? 'Ожидает оплаты' : 'Неактивна'; }
}

// -------------------------
// Инициализация
// -------------------------
window.dashboardApp = new DashboardApp();