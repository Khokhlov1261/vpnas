/**
 * Dashboard JavaScript для личного кабинета SecureLink
 * - Авторизация через Telegram WebApp
 * - Покупка тарифов (редирект в YooKassa)
 * - Отображение конфигов (.conf и QR) после оплаты
 */

class DashboardApp {
    constructor() {
        this.currentUser = null;
        this.authToken = null;
        this.telegramWebApp = null;
        this.currentSection = 'dashboard';
        this.init();
    }

    async init() {
        try {
            this.initTelegramWebApp();
            await this.checkAuth();
            this.initUI();
            await this.loadSectionData(this.currentSection);
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

            console.log('Telegram Web App initialized:', this.telegramWebApp.initDataUnsafe);
        }
    }

    async checkAuth() {
        this.authToken = localStorage.getItem('authToken');
        if (this.authToken) {
            try {
                const data = await this.apiCall('/auth/me');
                this.currentUser = data.user;
                return;
            } catch {
                localStorage.removeItem('authToken');
            }
        }

        if (this.telegramWebApp?.initData) {
            await this.authenticateWithTelegram();
        } else {
            window.location.href = '/';
        }
    }

    async authenticateWithTelegram() {
        try {
            const response = await fetch('/auth/telegram', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ init_data: this.telegramWebApp.initData })
            });
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || 'Ошибка авторизации');
            this.authToken = data.token;
            this.currentUser = data.user;
            localStorage.setItem('authToken', this.authToken);
            this.showToast('Успешная авторизация!', 'success');
        } catch (err) {
            console.error('Ошибка авторизации через Telegram:', err);
            this.showToast('Ошибка авторизации', 'error');
            window.location.href = '/';
        }
    }

    initUI() {
        this.initNavigation();
        this.initButtons();
        this.initModals();
        this.updateUserInfo();
    }

    initNavigation() {
        document.querySelectorAll('.nav-link').forEach(link => {
            link.addEventListener('click', async e => {
                e.preventDefault();
                const section = link.dataset.section;
                await this.showSection(section);
            });
        });
    }

    initButtons() {
        document.getElementById('logoutBtn')?.addEventListener('click', () => this.logout());
        document.getElementById('renewSubscriptionBtn')?.addEventListener('click', () => window.location.href = '/');
        document.getElementById('buyNewSubscriptionBtn')?.addEventListener('click', () => window.location.href = '/');
        document.getElementById('saveSettingsBtn')?.addEventListener('click', () => this.saveSettings());
        document.getElementById('markAllReadBtn')?.addEventListener('click', () => this.markAllNotificationsRead());
    }

    initModals() {
        document.getElementById('configModalClose')?.addEventListener('click', () => this.closeModal('configModal'));
        document.getElementById('configModal')?.addEventListener('click', e => {
            if (e.target.id === 'configModal') this.closeModal('configModal');
        });
    }

    updateUserInfo() {
        if (!this.currentUser) return;
        const avatar = document.getElementById('avatarPlaceholder');
        if (avatar) avatar.textContent = (this.currentUser.first_name?.[0] || 'U').toUpperCase();
        const username = document.getElementById('username');
        if (username) username.textContent = `@${this.currentUser.username || 'user'}`;
    }

    async showSection(sectionName) {
        document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));
        document.querySelector(`[data-section="${sectionName}"]`)?.classList.add('active');
        document.querySelectorAll('.content-section').forEach(s => s.classList.remove('active'));
        const sectionEl = document.getElementById(`${sectionName}Section`);
        if (sectionEl) sectionEl.classList.add('active');
        this.currentSection = sectionName;
        await this.loadSectionData(sectionName);
    }

    async loadSectionData(sectionName) {
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
            const subs = await this.apiCall('/api/user/subscriptions');
            this.updateDashboardSubscriptions(subs.subscriptions);
            const traffic = await this.apiCall('/api/user/traffic');
            this.updateDashboardTraffic(traffic);
        } catch (err) { console.error(err); }
    }

    
    updateDashboardSubscriptions(subscriptions) {
        const activeSubscription = subscriptions.find(sub => sub.status === 'paid' && !this.isExpired(sub.expires_at));
        
        const activeSubscriptionEl = document.getElementById('activeSubscription');
        const subscriptionExpiryEl = document.getElementById('subscriptionExpiry');
        const userPlanEl = document.getElementById('userPlan');
        const renewBtn = document.getElementById('renewSubscriptionBtn');
        
        if (activeSubscription) {
            if (activeSubscriptionEl) {
                activeSubscriptionEl.textContent = activeSubscription.plan;
            }
            if (subscriptionExpiryEl) {
                subscriptionExpiryEl.textContent = `Действует до ${this.formatDate(activeSubscription.expires_at)}`;
            }
            if (userPlanEl) {
                userPlanEl.textContent = activeSubscription.plan;
            }
            if (renewBtn) {
                renewBtn.style.display = 'inline-flex';
            }
        } else {
            if (activeSubscriptionEl) {
                activeSubscriptionEl.textContent = 'Нет активной подписки';
            }
            if (subscriptionExpiryEl) {
                subscriptionExpiryEl.textContent = '—';
            }
            if (userPlanEl) {
                userPlanEl.textContent = 'Без подписки';
            }
            if (renewBtn) {
                renewBtn.style.display = 'inline-flex';
            }
        }
    }
    
    updateDashboardTraffic(trafficData) {
        const totalRx = trafficData.total_rx || 0;
        const totalTx = trafficData.total_tx || 0;
        const totalTraffic = totalRx + totalTx;
        
        const todayTrafficEl = document.getElementById('todayTraffic');
        const trafficDetailsEl = document.getElementById('trafficDetails');
        const connectionStatusEl = document.getElementById('connectionStatus');
        const connectionIPEl = document.getElementById('connectionIP');
        
        if (todayTrafficEl) {
            todayTrafficEl.textContent = this.formatBytes(totalTraffic);
        }
        if (trafficDetailsEl) {
            trafficDetailsEl.textContent = `↓ ${this.formatBytes(totalRx)} ↑ ${this.formatBytes(totalTx)}`;
        }
        
        // Статус подключения
        const activeConnection = trafficData.traffic?.find(t => t.online);
        if (activeConnection) {
            if (connectionStatusEl) {
                connectionStatusEl.textContent = 'Онлайн';
                connectionStatusEl.className = 'stat-value online';
            }
            if (connectionIPEl) {
                connectionIPEl.textContent = `IP: ${activeConnection.client_ip}`;
            }
        } else {
            if (connectionStatusEl) {
                connectionStatusEl.textContent = 'Офлайн';
                connectionStatusEl.className = 'stat-value offline';
            }
            if (connectionIPEl) {
                connectionIPEl.textContent = '—';
            }
        }
    }
    
    async loadSubscriptions() {
        const container = document.getElementById('subscriptionsList');
        if (!container) return;
        
        container.innerHTML = '<div class="loading">Загрузка подписок...</div>';
        
        try {
            const response = await this.apiCall('/api/user/subscriptions');
            if (response.ok) {
                this.renderSubscriptions(response.subscriptions);
            }
        } catch (error) {
            console.error('Ошибка загрузки подписок:', error);
            container.innerHTML = '<div class="error">Ошибка загрузки подписок</div>';
        }
    }
    
    renderSubscriptions(subscriptions) {
        const container = document.getElementById('subscriptionsList');
        if (!container) return;
        
        if (subscriptions.length === 0) {
            container.innerHTML = '<div class="empty-state">У вас пока нет подписок</div>';
            return;
        }
        
        container.innerHTML = subscriptions.map(sub => `
            <div class="subscription-item">
                <div class="item-header">
                    <div class="item-title">${sub.plan}</div>
                    <div class="item-status ${this.getStatusClass(sub.status, sub.expires_at)}">
                        ${this.getStatusText(sub.status, sub.expires_at)}
                    </div>
                </div>
                <div class="item-details">
                    <div class="detail-item">
                        <div class="detail-label">Цена</div>
                        <div class="detail-value">${sub.price} ₽</div>
                    </div>
                    <div class="detail-item">
                        <div class="detail-label">Дата создания</div>
                        <div class="detail-value">${this.formatDate(sub.created_at)}</div>
                    </div>
                    <div class="detail-item">
                        <div class="detail-label">Действует до</div>
                        <div class="detail-value">${sub.expires_at ? this.formatDate(sub.expires_at) : '—'}</div>
                    </div>
                </div>
                <div class="item-actions">
                    ${sub.has_config ? `
                        <button class="btn btn-primary" onclick="dashboardApp.downloadConfig(${sub.id})">
                            Скачать конфиг
                        </button>
                        <button class="btn btn-secondary" onclick="dashboardApp.showQRCode(${sub.id})">
                            QR-код
                        </button>
                    ` : ''}
                    ${this.isExpired(sub.expires_at) ? `
                        <button class="btn btn-success" onclick="window.location.href='/'">
                            Продлить
                        </button>
                    ` : ''}
                </div>
            </div>
        `).join('');
    }
    
    async loadConfigs() {
        const container = document.getElementById('configsList');
        if (!container) return;
        
        container.innerHTML = '<div class="loading">Загрузка конфигураций...</div>';
        
        try {
            const response = await this.apiCall('/api/user/configs');
            if (response.ok) {
                this.renderConfigs(response.configs);
            }
        } catch (error) {
            console.error('Ошибка загрузки конфигураций:', error);
            container.innerHTML = '<div class="error">Ошибка загрузки конфигураций</div>';
        }
    }
    
    renderConfigs(configs) {
        const container = document.getElementById('configsList');
        if (!container) return;
        
        if (configs.length === 0) {
            container.innerHTML = '<div class="empty-state">У вас пока нет конфигураций</div>';
            return;
        }
        
        container.innerHTML = configs.map(config => `
            <div class="config-item">
                <div class="item-header">
                    <div class="item-title">${config.plan}</div>
                    <div class="item-status ${this.getStatusClass(config.status, config.expires_at)}">
                        ${this.getStatusText(config.status, config.expires_at)}
                    </div>
                </div>
                <div class="item-details">
                    <div class="detail-item">
                        <div class="detail-label">Дата создания</div>
                        <div class="detail-value">${this.formatDate(config.created_at)}</div>
                    </div>
                    <div class="detail-item">
                        <div class="detail-label">Действует до</div>
                        <div class="detail-value">${config.expires_at ? this.formatDate(config.expires_at) : '—'}</div>
                    </div>
                    <div class="detail-item">
                        <div class="detail-label">Файл</div>
                        <div class="detail-value">${config.has_file ? 'Доступен' : 'Не найден'}</div>
                    </div>
                </div>
                <div class="item-actions">
                    ${config.has_file ? `
                        <button class="btn btn-primary" onclick="dashboardApp.downloadConfig(${config.id})">
                            Скачать .conf
                        </button>
                        <button class="btn btn-secondary" onclick="dashboardApp.showQRCode(${config.id})">
                            Показать QR-код
                        </button>
                    ` : `
                        <div class="text-muted">Конфигурация недоступна</div>
                    `}
                </div>
            </div>
        `).join('');
    }
    
    async loadTrafficStats() {
        const container = document.getElementById('trafficStats');
        if (!container) return;
        
        container.innerHTML = '<div class="loading">Загрузка статистики...</div>';
        
        try {
            const response = await this.apiCall('/api/user/traffic');
            if (response.ok) {
                this.renderTrafficStats(response);
            }
        } catch (error) {
            console.error('Ошибка загрузки статистики трафика:', error);
            container.innerHTML = '<div class="error">Ошибка загрузки статистики</div>';
        }
    }
    
    renderTrafficStats(trafficData) {
        const container = document.getElementById('trafficStats');
        if (!container) return;
        
        if (!trafficData.traffic || trafficData.traffic.length === 0) {
            container.innerHTML = '<div class="empty-state">Нет данных о трафике</div>';
            return;
        }
        
        container.innerHTML = `
            <div class="traffic-summary">
                <div class="stats-card">
                    <div class="stats-icon">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M3 3v18h18"></path>
                            <path d="M18.7 8l-5.1 5.2-2.8-2.7L7 14.3"></path>
                        </svg>
                    </div>
                    <div class="stats-content">
                        <h3>Общий трафик</h3>
                        <div class="stat-value">${this.formatBytes(trafficData.total_rx + trafficData.total_tx)}</div>
                        <div class="stat-label">↓ ${this.formatBytes(trafficData.total_rx)} ↑ ${this.formatBytes(trafficData.total_tx)}</div>
                    </div>
                </div>
            </div>
            <div class="traffic-details">
                ${trafficData.traffic.map(t => `
                    <div class="traffic-item">
                        <div class="traffic-header">
                            <div class="traffic-plan">${t.plan}</div>
                            <div class="traffic-status ${t.online ? 'online' : 'offline'}">
                                ${t.online ? 'Онлайн' : 'Офлайн'}
                            </div>
                        </div>
                        <div class="traffic-stats">
                            <div class="traffic-stat">
                                <span class="label">IP:</span>
                                <span class="value">${t.client_ip}</span>
                            </div>
                            <div class="traffic-stat">
                                <span class="label">Скачано:</span>
                                <span class="value">${this.formatBytes(t.rx_bytes)}</span>
                            </div>
                            <div class="traffic-stat">
                                <span class="label">Загружено:</span>
                                <span class="value">${this.formatBytes(t.tx_bytes)}</span>
                            </div>
                            <div class="traffic-stat">
                                <span class="label">Скорость:</span>
                                <span class="value">↓ ${this.formatSpeed(t.speed_rx)} ↑ ${this.formatSpeed(t.speed_tx)}</span>
                            </div>
                        </div>
                    </div>
                `).join('')}
            </div>
        `;
    }
    
    async loadNotifications() {
        const container = document.getElementById('notificationsList');
        if (!container) return;
        
        container.innerHTML = '<div class="loading">Загрузка уведомлений...</div>';
        
        try {
            const response = await this.apiCall('/api/user/notifications');
            if (response.ok) {
                this.renderNotifications(response.notifications);
                this.updateNotificationBadge(response.unread_count);
            }
        } catch (error) {
            console.error('Ошибка загрузки уведомлений:', error);
            container.innerHTML = '<div class="error">Ошибка загрузки уведомлений</div>';
        }
    }
    
    renderNotifications(notifications) {
        const container = document.getElementById('notificationsList');
        if (!container) return;
        
        if (notifications.length === 0) {
            container.innerHTML = '<div class="empty-state">У вас нет уведомлений</div>';
            return;
        }
        
        container.innerHTML = notifications.map(notification => `
            <div class="notification-item ${notification.is_read ? '' : 'unread'}">
                <div class="notification-header">
                    <div class="notification-title">${notification.title}</div>
                    <div class="notification-time">${this.formatDate(notification.created_at)}</div>
                </div>
                <div class="notification-message">${notification.message}</div>
                ${!notification.is_read ? `
                    <div class="notification-actions">
                        <button class="btn btn-ghost btn-sm" onclick="dashboardApp.markNotificationRead(${notification.id})">
                            Отметить как прочитанное
                        </button>
                    </div>
                ` : ''}
            </div>
        `).join('');
    }
    
    async loadSettings() {
        if (!this.currentUser) return;
        
        // Заполняем поля настроек
        const usernameInput = document.getElementById('usernameInput');
        const emailInput = document.getElementById('emailInput');
        const languageSelect = document.getElementById('languageSelect');
        
        if (usernameInput) {
            usernameInput.value = this.currentUser.username || '';
        }
        if (emailInput) {
            emailInput.value = this.currentUser.email || '';
        }
        if (languageSelect) {
            languageSelect.value = this.currentUser.language_code || 'ru';
        }
    }
    
    async downloadConfig(orderId) {
        try {
            const response = await fetch(`/download/${orderId}`, {
                headers: {
                    'Authorization': `Bearer ${this.authToken}`
                }
            });
            
            if (response.ok) {
                const blob = await response.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `securelink_${orderId}.conf`;
                document.body.appendChild(a);
                a.click();
                window.URL.revokeObjectURL(url);
                document.body.removeChild(a);
                
                this.showToast('Конфигурация скачана', 'success');
            } else {
                throw new Error('Ошибка скачивания');
            }
        } catch (error) {
            console.error('Ошибка скачивания конфигурации:', error);
            this.showToast('Ошибка скачивания конфигурации', 'error');
        }
    }
    
    async showQRCode(orderId) {
        try {
            const response = await fetch(`/qr/${orderId}`, {
                headers: {
                    'Authorization': `Bearer ${this.authToken}`
                }
            });
            
            if (response.ok) {
                const blob = await response.blob();
                const img = new Image();
                img.onload = () => {
                    const canvas = document.getElementById('qrCanvas');
                    const ctx = canvas.getContext('2d');
                    canvas.width = img.width;
                    canvas.height = img.height;
                    ctx.drawImage(img, 0, 0);
                    
                    this.showModal('configModal');
                    document.getElementById('qrContainer').style.display = 'block';
                };
                img.src = URL.createObjectURL(blob);
            } else {
                throw new Error('Ошибка загрузки QR-кода');
            }
        } catch (error) {
            console.error('Ошибка загрузки QR-кода:', error);
            this.showToast('Ошибка загрузки QR-кода', 'error');
        }
    }
    
    async markNotificationRead(notificationId) {
        try {
            const response = await this.apiCall(`/api/user/notifications/${notificationId}/read`, 'POST');
            if (response.ok) {
                this.showToast('Уведомление отмечено как прочитанное', 'success');
                await this.loadNotifications();
            }
        } catch (error) {
            console.error('Ошибка обновления уведомления:', error);
            this.showToast('Ошибка обновления уведомления', 'error');
        }
    }
    
    async markAllNotificationsRead() {
        // Реализация для отметки всех уведомлений как прочитанных
        this.showToast('Функция в разработке', 'info');
    }
    
    async saveSettings() {
        const email = document.getElementById('emailInput')?.value;
        const language = document.getElementById('languageSelect')?.value;
        
        try {
            // Здесь будет API для сохранения настроек
            this.showToast('Настройки сохранены', 'success');
        } catch (error) {
            console.error('Ошибка сохранения настроек:', error);
            this.showToast('Ошибка сохранения настроек', 'error');
        }
    }
    
    async logout() {
        try {
            if (this.authToken) {
                await this.apiCall('/auth/logout', 'POST');
            }
        } catch (error) {
            console.error('Ошибка выхода:', error);
        } finally {
            localStorage.removeItem('authToken');
            this.authToken = null;
            this.currentUser = null;
            window.location.href = '/';
        }
    }
    
    // Утилиты
    async apiCall(endpoint, method = 'GET', body = null) {
        const options = {
            method,
            headers: {
                'Content-Type': 'application/json',
            }
        };
        
        if (this.authToken) {
            options.headers['Authorization'] = `Bearer ${this.authToken}`;
        }
        
        if (body) {
            options.body = JSON.stringify(body);
        }
        
        const response = await fetch(endpoint, options);
        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.error || 'Ошибка API');
        }
        
        return data;
    }
    
    showModal(modalId) {
        const modal = document.getElementById(modalId);
        if (modal) {
            modal.classList.add('active');
        }
    }
    
    closeModal(modalId) {
        const modal = document.getElementById(modalId);
        if (modal) {
            modal.classList.remove('active');
        }
    }
    
    showToast(message, type = 'info') {
        const container = document.getElementById('toastContainer');
        if (!container) return;
        
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.innerHTML = `
            <div class="toast-content">
                <span>${message}</span>
            </div>
        `;
        
        container.appendChild(toast);
        
        setTimeout(() => {
            toast.remove();
        }, 5000);
    }
    
    updateNotificationBadge(count) {
        const badge = document.getElementById('notificationBadge');
        if (badge) {
            if (count > 0) {
                badge.textContent = count;
                badge.style.display = 'inline-block';
            } else {
                badge.style.display = 'none';
            }
        }
    }
    
    formatBytes(bytes) {
        if (bytes === 0) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }
    
    formatSpeed(bytesPerSec) {
        if (bytesPerSec === 0) return '0 B/s';
        return this.formatBytes(bytesPerSec) + '/s';
    }
    
    formatDate(dateString) {
        if (!dateString) return '—';
        const date = new Date(dateString);
        return date.toLocaleDateString('ru-RU', {
            year: 'numeric',
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
        });
    }
    
    isExpired(expiresAt) {
        if (!expiresAt) return false;
        return new Date(expiresAt) < new Date();
    }
    
    getStatusClass(status, expiresAt) {
        if (this.isExpired(expiresAt)) return 'expired';
        if (status === 'paid') return 'active';
        if (status === 'pending') return 'pending';
        return 'expired';
    }
    
    getStatusText(status, expiresAt) {
        if (this.isExpired(expiresAt)) return 'Истекла';
        if (status === 'paid') return 'Активна';
        if (status === 'pending') return 'Ожидает оплаты';
        return 'Неактивна';
    }
}


async downloadConfig(configId) {
    try {
        const response = await this.apiCall(`/api/configs/${configId}/download`);
        if (response.ok && response.url) {
            window.location.href = response.url; // редирект на скачивание .conf
        } else {
            this.showToast('Ошибка при скачивании файла', 'error');
        }
    } catch (err) {
        console.error('downloadConfig error', err);
        this.showToast('Ошибка скачивания', 'error');
    }
}

async showQRCode(configId) {
    try {
        const response = await this.apiCall(`/api/configs/${configId}/qr`);
        if (response.ok && response.qr_url) {
            // открыть модальное окно с QR
            const img = document.getElementById('qrImage');
            img.src = response.qr_url;
            this.openModal('configModal');
        } else {
            this.showToast('QR-код недоступен', 'error');
        }
    } catch (err) {
        console.error('showQRCode error', err);
        this.showToast('Ошибка загрузки QR', 'error');
    }
}


// Инициализация
let dashboardApp;
document.addEventListener('DOMContentLoaded', () => {
    dashboardApp = new DashboardApp();
    window.dashboardApp = dashboardApp;
});