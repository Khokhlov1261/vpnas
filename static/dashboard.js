/**
 * Dashboard JavaScript для личного кабинета SecureLink
 * - Авто-логин через Telegram WebApp (initData)
 * - Покупка тарифов из мини-приложения (редирект в YooKassa)
 * - Отображение конфигов (.conf и QR) после оплаты
 */

async function fetchJSON(url, opts) {
  const res = await fetch(url, opts);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

async function ensureJwt() {
  let token = localStorage.getItem('jwt');
  if (token) return token;
  const tg = window.Telegram && window.Telegram.WebApp;
  const initData = tg && tg.initData;
  if (!initData) return null;
  const resp = await fetch('/auth/telegram', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ init_data: initData })
  });
  const data = await resp.json();
  if (data && data.token) {
    localStorage.setItem('jwt', data.token);
    return data.token;
  }
  return null;
}

async function loadUser() {
  try {
    const token = await ensureJwt();
    if (!token) return;
    const data = await fetchJSON('/auth/me', { headers: { 'Authorization': `Bearer ${token}` } });
    const user = data && data.user ? data.user : null;
    if (!user) return;
    // Заполним боковую панель
    document.getElementById('username').textContent = user.username ? `@${user.username}` : (user.first_name || 'User');
    document.getElementById('avatarPlaceholder').textContent = (user.first_name || 'U').slice(0,1).toUpperCase();
  } catch (e) {
    console.error('loadUser error', e);
  }
}

async function loadConfigs() {
  try {
    const token = await ensureJwt();
    if (!token) return;
    const res = await fetchJSON('/api/user/configs', { headers: { 'Authorization': `Bearer ${token}` } });
    const listEl = document.getElementById('configsList');
    const quick = document.getElementById('quickConfig');
    const quickDl = document.getElementById('quickDownload');
    const quickShowQR = document.getElementById('quickShowQR');
    const quickQR = document.getElementById('quickQR');
    const quickQRImg = document.getElementById('quickQRImg');
    listEl.innerHTML = '';
    if (!res.configs || res.configs.length === 0) {
      listEl.innerHTML = '<div class="empty">Конфигурации пока отсутствуют</div>';
      quick.style.display = 'none';
      return;
    }
    // Показать первую конфигурацию как быстрый доступ
    const first = res.configs[0];
    if (first && first.has_file) {
      quick.style.display = '';
      quickDl.href = first.download_url;
      quickShowQR.onclick = async () => {
        quickQR.style.display = '';
        quickQRImg.src = first.qr_url;
        quickQRImg.onload = () => {};
      };
    } else {
      quick.style.display = 'none';
    }
    res.configs.forEach(cfg => {
      const item = document.createElement('div');
      item.className = 'config-item';
      const actions = [];
      if (cfg.download_url) actions.push(`<a class="btn" href="${cfg.download_url}">Скачать .conf</a>`);
      if (cfg.qr_url) actions.push(`<a class="btn btn-secondary" target="_blank" href="${cfg.qr_url}">Открыть QR</a>`);
      item.innerHTML = `
        <div class="config-meta">
          <div class="config-plan">${cfg.plan || ''}</div>
          <div class="config-dates">${cfg.created_at || ''} → ${cfg.expires_at || ''}</div>
          <div class="config-status ${cfg.status}">${cfg.status}</div>
        </div>
        <div class="config-actions">${actions.join(' ')}</div>
      `;
      listEl.appendChild(item);
    });
  } catch (e) {
    console.error('loadConfigs error', e);
  }
}

async function createPayment(planId, phone) {
  try {
    const tg = window.Telegram && window.Telegram.WebApp;
    const tgUser = tg && tg.initDataUnsafe && tg.initDataUnsafe.user;
    const telegramId = tgUser && tgUser.id;
    if (telegramId) {
      await fetch('/bot/link-phone', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ phone, telegram_id: telegramId })
      });
    }
    const resp = await fetch('/create-payment', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: phone, plan_id: planId })
    });
    const data = await resp.json();
    if (data && data.confirmation_url) {
      window.location.href = data.confirmation_url;
    } else {
      alert('Не удалось создать платёж');
    }
  } catch (e) {
    console.error('createPayment error', e);
    alert('Ошибка создания платежа');
  }
}

async function loadSubscriptions() {
  try {
    const token = await ensureJwt();
    if (!token) return;
    const res = await fetchJSON('/api/user/subscriptions', { headers: { 'Authorization': `Bearer ${token}` } });
    const listEl = document.getElementById('subscriptionsList');
    listEl.innerHTML = '';

    const plans = [
      { id: 1, name: '1 месяц', price: 99 },
      { id: 2, name: '6 месяцев', price: 499 },
      { id: 3, name: '1 год', price: 999 }
    ];

    const plansWrap = document.createElement('div');
    plansWrap.className = 'plans-grid';
    plans.forEach(p => {
      const card = document.createElement('div');
      card.className = 'plan-card';
      card.innerHTML = `
        <h3>${p.name}</h3>
        <div class="price">${p.price} ₽</div>
        <button class="btn btn-primary" data-plan="${p.id}">Оплатить</button>
      `;
      plansWrap.appendChild(card);
    });
    listEl.appendChild(plansWrap);

    listEl.addEventListener('click', async (e) => {
      const btn = e.target.closest('button[data-plan]');
      if (!btn) return;
      const planId = parseInt(btn.getAttribute('data-plan'), 10);
      const phone = prompt('Введите номер телефона для оформления оплаты:');
      if (!phone) return;
      await createPayment(planId, phone);
    }, { once: true });

    if (res.subscriptions && res.subscriptions.length) {
      const myList = document.createElement('div');
      myList.className = 'my-subscriptions';
      res.subscriptions.forEach(s => {
        const row = document.createElement('div');
        row.className = 'sub-row';
        row.innerHTML = `
          <div class="sub-plan">${s.plan}</div>
          <div class="sub-dates">${s.created_at || ''} → ${s.expires_at || ''}</div>
          <div class="sub-status ${s.status}">${s.status}</div>
        `;
        myList.appendChild(row);
      });
      listEl.appendChild(myList);
    }
  } catch (e) {
    console.error('loadSubscriptions error', e);
  }
}

async function loadTraffic() {
  try {
    const token = await ensureJwt();
    if (!token) return;
    const res = await fetchJSON('/api/user/traffic', { headers: { 'Authorization': `Bearer ${token}` } });
    // Простое заполнение сводки
    const totalRx = (res.total_rx || 0) / (1024*1024);
    const totalTx = (res.total_tx || 0) / (1024*1024);
    document.getElementById('todayTraffic').textContent = `${totalRx.toFixed(1)} MB`;
    document.getElementById('trafficDetails').textContent = `↓ ${totalRx.toFixed(1)} MB ↑ ${totalTx.toFixed(1)} MB`;
  } catch (e) {
    console.error('loadTraffic error', e);
  }
}

document.addEventListener('DOMContentLoaded', () => {
  const navLinks = document.querySelectorAll('.nav-link');
  if (navLinks && navLinks.length) {
    navLinks.forEach(link => {
      link.addEventListener('click', e => {
        e.preventDefault();
        const section = link.getAttribute('data-section');
        document.querySelectorAll('.content-section').forEach(s => s.classList.remove('active'));
        document.getElementById(section + 'Section').classList.add('active');
        document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));
        link.classList.add('active');
        if (section === 'configs') loadConfigs();
        if (section === 'subscriptions') loadSubscriptions();
        if (section === 'traffic') loadTraffic();
      });
    });
  }

  (async () => {
    await ensureJwt();
    await loadUser();
    // По умолчанию показываем конфиги (mobile-first)
    await loadConfigs();
    // Остальные данные подгрузим фоном
    loadSubscriptions();
    loadTraffic();
  })();
});

class DashboardApp {
    constructor() {
        this.currentUser = null;
        this.authToken = null;
        this.currentSection = 'dashboard';
        this.telegramWebApp = null;
        
        this.init();
    }
    
    async init() {
        try {
            // Инициализация Telegram Web App
            this.initTelegramWebApp();
            
            // Проверка авторизации
            await this.checkAuth();
            
            // Инициализация UI
            this.initUI();
            
            // Загрузка данных
            await this.loadDashboardData();
            
        } catch (error) {
            console.error('Ошибка инициализации:', error);
            this.showToast('Ошибка загрузки приложения', 'error');
        }
    }
    
    initTelegramWebApp() {
        if (window.Telegram?.WebApp) {
            this.telegramWebApp = window.Telegram.WebApp;
            this.telegramWebApp.ready();
            this.telegramWebApp.expand();
            
            // Настройка темы
            if (this.telegramWebApp.colorScheme === 'dark') {
                document.body.classList.add('telegram-dark');
            }
            
            // Настройка главной кнопки
            this.telegramWebApp.MainButton.setText('🚀 Открыть VPN');
            this.telegramWebApp.MainButton.show();
            this.telegramWebApp.MainButton.onClick(() => {
                window.location.href = '/';
            });
            
            console.log('Telegram Web App initialized:', this.telegramWebApp.initDataUnsafe);
        }
    }
    async checkAuth() {
    this.authToken = localStorage.getItem('authToken');  // 1. Сначала проверяем локальный токен

    if (this.authToken) {
        try {
            const response = await this.apiCall('/auth/me'); // 2. Проверяем токен на сервере
            this.currentUser = response.user;               // 3. Если токен валидный, сохраняем пользователя
            return;
        } catch {
            localStorage.removeItem('authToken');          // 4. Если токен невалидный, удаляем
        }
    }

    // 5. Если токена нет или он невалидный, проверяем данные Telegram
    if (this.telegramWebApp?.initDataUnsafe?.user) {
        await this.authenticateWithTelegram();            // 6. Авторизация через Telegram
    } else {
        window.location.href = '/';                       // 7. Если нет ничего — редирект на главную
    }
}
        
        // Если нет токена или он недействителен, пробуем авторизацию через Telegram
        if (this.telegramWebApp?.initDataUnsafe?.user) {
            await this.authenticateWithTelegram();
        } else {
            // Перенаправляем на главную страницу для авторизации
            window.location.href = '/';
        }
    }
    
    async authenticateWithTelegram() {
        try {
            const initData = this.telegramWebApp.initData;
            
            const response = await fetch('/auth/telegram', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    init_data: initData
                })
            });
            
            const data = await response.json();
            
            if (response.ok) {
                this.authToken = data.token;
                this.currentUser = data.user;
                localStorage.setItem('authToken', this.authToken);
                this.showToast('Успешная авторизация!', 'success');
            } else {
                throw new Error(data.error || 'Ошибка авторизации');
            }
        } catch (error) {
            console.error('Ошибка авторизации через Telegram:', error);
            this.showToast('Ошибка авторизации', 'error');
            window.location.href = '/';
        }
    }
    
    initUI() {
        // Навигация
        this.initNavigation();
        
        // Кнопки
        this.initButtons();
        
        // Модальные окна
        this.initModals();
        
        // Обновление информации о пользователе
        this.updateUserInfo();
    }
    
    initNavigation() {
        const navLinks = document.querySelectorAll('.nav-link');
        navLinks.forEach(link => {
            link.addEventListener('click', (e) => {
                e.preventDefault();
                const section = link.dataset.section;
                this.showSection(section);
            });
        });
    }
    
    initButtons() {
        // Выход
        document.getElementById('logoutBtn')?.addEventListener('click', () => {
            this.logout();
        });
        
        // Продление подписки
        document.getElementById('renewSubscriptionBtn')?.addEventListener('click', () => {
            window.location.href = '/';
        });
        
        // Покупка новой подписки
        document.getElementById('buyNewSubscriptionBtn')?.addEventListener('click', () => {
            window.location.href = '/';
        });
        
        // Сохранение настроек
        document.getElementById('saveSettingsBtn')?.addEventListener('click', () => {
            this.saveSettings();
        });
        
        // Отметить все уведомления как прочитанные
        document.getElementById('markAllReadBtn')?.addEventListener('click', () => {
            this.markAllNotificationsRead();
        });
    }
    
    initModals() {
        // Закрытие модального окна
        document.getElementById('configModalClose')?.addEventListener('click', () => {
            this.closeModal('configModal');
        });
        
        // Закрытие по клику вне модального окна
        document.getElementById('configModal')?.addEventListener('click', (e) => {
            if (e.target.id === 'configModal') {
                this.closeModal('configModal');
            }
        });
    }
    
    updateUserInfo() {
        if (!this.currentUser) return;
        
        // Аватар
        const avatarPlaceholder = document.getElementById('avatarPlaceholder');
        if (avatarPlaceholder) {
            const firstLetter = this.currentUser.first_name?.[0] || this.currentUser.username?.[0] || 'U';
            avatarPlaceholder.textContent = firstLetter.toUpperCase();
        }
        
        // Имя пользователя
        const username = document.getElementById('username');
        if (username) {
            username.textContent = `@${this.currentUser.username || 'user'}`;
        }
        
        // План пользователя (будет обновлен после загрузки подписок)
        const userPlan = document.getElementById('userPlan');
        if (userPlan) {
            userPlan.textContent = 'Загрузка...';
        }
    }
    
    async showSection(sectionName) {
        // Обновляем активную ссылку
        document.querySelectorAll('.nav-link').forEach(link => {
            link.classList.remove('active');
        });
        document.querySelector(`[data-section="${sectionName}"]`)?.classList.add('active');
        
        // Скрываем все секции
        document.querySelectorAll('.content-section').forEach(section => {
            section.classList.remove('active');
        });
        
        // Показываем нужную секцию
        const targetSection = document.getElementById(`${sectionName}Section`);
        if (targetSection) {
            targetSection.classList.add('active');
            this.currentSection = sectionName;
            
            // Загружаем данные для секции
            await this.loadSectionData(sectionName);
        }
    }
    
    async loadSectionData(sectionName) {
        switch (sectionName) {
            case 'dashboard':
                await this.loadDashboardData();
                break;
            case 'subscriptions':
                await this.loadSubscriptions();
                break;
            case 'configs':
                await this.loadConfigs();
                break;
            case 'traffic':
                await this.loadTrafficStats();
                break;
            case 'notifications':
                await this.loadNotifications();
                break;
            case 'settings':
                await this.loadSettings();
                break;
        }
    }
    
    async loadDashboardData() {
        try {
            // Загружаем подписки для dashboard
            const subscriptionsResponse = await this.apiCall('/api/user/subscriptions');
            if (subscriptionsResponse.ok) {
                this.updateDashboardSubscriptions(subscriptionsResponse.subscriptions);
            }
            
            // Загружаем статистику трафика
            const trafficResponse = await this.apiCall('/api/user/traffic');
            if (trafficResponse.ok) {
                this.updateDashboardTraffic(trafficResponse);
            }
            
        } catch (error) {
            console.error('Ошибка загрузки данных dashboard:', error);
        }
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

// Инициализация приложения
let dashboardApp;
document.addEventListener('DOMContentLoaded', () => {
    dashboardApp = new DashboardApp();
});

// Экспорт для использования в HTML
window.dashboardApp = dashboardApp;
