// --- Константы тарифов ---
const PLANS = [
  { id: 9, name: "3 дня free", price_display: "0 ₽" }, // бесплатный пробный тариф
  { id: 1, name: "1 месяц", price_display:  "99 ₽" },
  { id: 2, name: "6 месяцев", price_display:  "499 ₽" },
  { id: 3, name: "12 месяцев", price_display:  "999 ₽" },
];



// --- DOM элементы ---
const plansContainer = document.getElementById('plans');
const selectedPlanEl = document.getElementById('selectedPlan');
const emailInput = document.getElementById('email');
const payBtn = document.getElementById('payBtn');
const statusEl = document.getElementById('status');

let selectedPlan = null;
let freeTrialUsed = false; // флаг для блокировки повторного пробного периода

// --- Рендер тарифов ---
function renderPlans() {
  plansContainer.innerHTML = '';
  PLANS.forEach(plan => {
    const el = document.createElement('div');
    el.className = 'plan';
    el.dataset.id = plan.id;
    el.innerHTML = `<div class="info"><h3>${plan.name}</h3></div><div class="price">${plan.price_display}</div>`;
    plansContainer.appendChild(el);
  });
}

// --- Выбор тарифа ---
plansContainer.addEventListener('click', (e) => {
  const planEl = e.target.closest('.plan');
  if (!planEl) return;
  const id = Number(planEl.dataset.id);
  selectedPlan = PLANS.find(p => p.id === id);
  selectedPlanEl.textContent = `${selectedPlan.name} — ${selectedPlan.price_display}`;
  statusEl.textContent = `Статус: выбран тариф "${selectedPlan.name}"`;
  document.querySelectorAll('.plan').forEach(p => p.classList.remove('selected'));
  planEl.classList.add('selected');
});

// --- Создание платежа или активация бесплатного тарифа ---
payBtn.addEventListener('click', async () => {
  const email = emailInput.value.trim();

  if (!selectedPlan) {
    alert('Выберите тариф');
    return;
  }
  if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    alert('Введите корректный email');
    return;
  }

  // Проверка повторного использования бесплатного пробного периода
  if (selectedPlan.id === 9 && freeTrialUsed) {
    alert("Бесплатный пробный период можно использовать только один раз");
    return;
  }

  payBtn.disabled = true;
  statusEl.textContent = 'Статус: обрабатываем заказ...';

  try {
    if (selectedPlan.id === 9) {
      // --- Бесплатный пробный период ---
      const response = await fetch('/free-trial', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email })
      });
      const data = await response.json();
      if (data.error) {
        alert(data.error);
        payBtn.disabled = false;
        return;
      }
      alert(data.message);
      statusEl.textContent = 'Статус: бесплатный пробный период активирован';
      freeTrialUsed = true; // блокируем повторное использование
      payBtn.disabled = false;
    } else {
      // --- Оплата через ЮKassa ---
      const response = await fetch('/create-payment', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, plan_id: selectedPlan.id })
      });
      const data = await response.json();
      if (data.error) {
        alert("Ошибка: " + data.error);
        payBtn.disabled = false;
        return;
      }
      if (!data.confirmation_url) {
        alert("Ошибка: URL подтверждения отсутствует");
        payBtn.disabled = false;
        return;
      }
      window.location.href = data.confirmation_url;
    }
  } catch (err) {
    console.error(err);
    alert("Ошибка при обработке заказа");
    payBtn.disabled = false;
  }
});

// --- Инициализация ---
renderPlans();