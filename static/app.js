const tg = window.Telegram?.WebApp;
let currentUser = null;

document.addEventListener('DOMContentLoaded', () => {
    if (!tg) {
        showScreen('error-screen');
        return;
    }
    tg.ready();
    tg.expand();
    const telegramId = tg.initDataUnsafe?.user?.id;
    if (!telegramId) {
        showScreen('error-screen');
        return;
    }
    window.telegramId = telegramId;
    initApp();
});

async function initApp() {
    showScreen('loading-screen');
    try {
        const meResponse = await fetch(`/api/me?telegram_id=${window.telegramId}`);
        if (meResponse.ok) {
            currentUser = await meResponse.json();
            showHomeScreen();
        } else {
            await loadBuildings();
            showScreen('register-screen');
        }
    } catch (error) {
        console.error('Ошибка инициализации:', error);
        showToast('Произошла ошибка. Попробуйте позже.');
        showScreen('error-screen');
    }
}

async function loadBuildings() {
    const select = document.getElementById('building-select');
    try {
        const resp = await fetch('/api/buildings');
        const buildings = await resp.json();
        select.innerHTML = '<option value="">Выберите дом...</option>';
        buildings.forEach(b => {
            const option = document.createElement('option');
            option.value = b.id;
            option.textContent = b.address;
            select.appendChild(option);
        });
    } catch (error) {
        console.error('Ошибка загрузки домов:', error);
    }
}

function showScreen(screenId) {
    document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
    document.getElementById(screenId).classList.add('active');
}

function showToast(message) {
    const toast = document.getElementById('toast');
    toast.textContent = message;
    toast.classList.add('show');
    setTimeout(() => toast.classList.remove('show'), 3000);
}

document.getElementById('register-btn').addEventListener('click', async () => {
    const buildingId = document.getElementById('building-select').value;
    const apartmentNumber = document.getElementById('apartment-input').value.trim();
    const fullName = document.getElementById('fullname-input').value.trim();
    const windowSide = document.getElementById('side-select').value;
    if (!buildingId || !apartmentNumber) {
        showToast('Выберите дом и введите номер квартиры');
        return;
    }
    try {
        const resp = await fetch(`/api/register?telegram_id=${window.telegramId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                building_id: parseInt(buildingId),
                apartment_number: apartmentNumber,
                full_name: fullName || null,
                window_side: windowSide,
            }),
        });
        if (resp.ok) {
            const data = await resp.json();
            currentUser = data.user;
            showHomeScreen();
        } else {
            const error = await resp.json();
            showToast(error.detail || 'Ошибка регистрации');
        }
    } catch (error) {
        console.error('Ошибка:', error);
        showToast('Ошибка сети');
    }
});

function showHomeScreen() {
    document.getElementById('user-info').textContent = `Вы зарегистрированы как ${currentUser.full_name || 'жилец'}`;
    showScreen('home-screen');
    loadMyRequests();
}

async function loadMyRequests() {
    try {
        const resp = await fetch(`/api/requests/my?telegram_id=${window.telegramId}`);
        if (resp.ok) {
            const requests = await resp.json();
            renderRequests(requests, document.getElementById('requests-container'));
        }
    } catch (error) {
        console.error('Ошибка загрузки заявок:', error);
    }
}

function renderRequests(requests, container) {
    container.innerHTML = '';
    if (!requests.length) {
        container.innerHTML = '<p style="text-align:center; color:var(--text-secondary)">У вас пока нет заявок</p>';
        return;
    }
    requests.forEach(req => {
        const div = document.createElement('div');
        div.className = 'request-item';
        const statusClass = req.status.replace(' ', '_');
        const serviceNames = {
            windows: 'Мытьё окон',
            balcony: 'Мытьё балкона',
            both: 'Комплекс',
            complaint: 'Претензия'
        };
        div.innerHTML = `
            <div class="service">${serviceNames[req.service_type] || req.service_type} #${req.id}</div>
            <span class="status ${statusClass}">${req.status}</span>
            ${req.comment ? `<div class="comment">${req.comment}</div>` : ''}
            ${req.status === 'completed' ? `<button class="btn secondary complaint-btn" data-id="${req.id}">Пожаловаться</button>` : ''}
        `;
        container.appendChild(div);
    });
    document.querySelectorAll('.complaint-btn').forEach(btn => {
        btn.addEventListener('click', () => openComplaintScreen(btn.dataset.id));
    });
}

document.getElementById('new-request-btn').addEventListener('click', () => showScreen('new-request-screen'));
document.getElementById('back-from-new').addEventListener('click', showHomeScreen);

document.getElementById('submit-request-btn').addEventListener('click', async () => {
    const serviceType = document.getElementById('service-type').value;
    const comment = document.getElementById('comment-input').value.trim();
    try {
        const resp = await fetch(`/api/requests?telegram_id=${window.telegramId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ service_type: serviceType, comment: comment || null }),
        });
        if (resp.ok) {
            showToast('Заявка создана');
            showHomeScreen();
        } else {
            const error = await resp.json();
            showToast(error.detail || 'Ошибка');
        }
    } catch (error) {
        console.error('Ошибка:', error);
        showToast('Ошибка сети');
    }
});

document.getElementById('my-requests-btn').addEventListener('click', () => {
    showScreen('my-requests-screen');
    loadMyRequestsForScreen();
});
document.getElementById('back-from-requests').addEventListener('click', showHomeScreen);

async function loadMyRequestsForScreen() {
    try {
        const resp = await fetch(`/api/requests/my?telegram_id=${window.telegramId}`);
        if (resp.ok) {
            const requests = await resp.json();
            renderRequests(requests, document.getElementById('my-requests-list'));
        }
    } catch (error) {
        console.error('Ошибка:', error);
    }
}

let complaintRequestId = null;
function openComplaintScreen(requestId) {
    complaintRequestId = requestId;
    document.getElementById('complaint-comment').value = '';
    document.getElementById('complaint-photos').value = '';
    showScreen('complaint-screen');
}
document.getElementById('back-from-complaint').addEventListener('click', showHomeScreen);

document.getElementById('submit-complaint-btn').addEventListener('click', async () => {
    const comment = document.getElementById('complaint-comment').value.trim();
    if (!comment) {
        showToast('Опишите проблему');
        return;
    }
    const photosInput = document.getElementById('complaint-photos');
    const photos = [];
    for (const file of photosInput.files) {
        if (photos.length >= 3) break;
        photos.push(await readFileAsBase64(file));
    }
    try {
        const resp = await fetch(`/api/requests/${complaintRequestId}/complaint?telegram_id=${window.telegramId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ request_id: complaintRequestId, comment, photos }),
        });
        if (resp.ok) {
            showToast('Претензия отправлена');
            showHomeScreen();
        } else {
            const error = await resp.json();
            showToast(error.detail || 'Ошибка');
        }
    } catch (error) {
        console.error('Ошибка:', error);
        showToast('Ошибка сети');
    }
});

function readFileAsBase64(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result);
        reader.onerror = reject;
        reader.readAsDataURL(file);
    });
}
