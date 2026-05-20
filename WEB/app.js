// app.js mínimo para teste
const SERVER_URL = window.location.origin;
let lastId = 0;

function updateStatus(text, cls) {
    const el = document.getElementById('status');
    if (el) { el.textContent = `Status: ${text}`; el.className = cls || ''; }
}

function appendMessage(user, text) {
    const container = document.getElementById('messages');
    if (!container) return;
    const div = document.createElement('div');
    div.className = user === 'SISTEMA' ? 'msg sys' : 'msg';
    div.innerHTML = user === 'SISTEMA' ? text : `<strong>[${user}]</strong> ${text}`;
    container.appendChild(div);
    container.scrollTop = container.scrollHeight;
}

async function pollMessages() {
    try {
        const res = await fetch(`${SERVER_URL}/messages?last_id=${lastId}`);
        if (res.ok) {
            const msgs = await res.json();
            for (const m of msgs) {
                if (m.id > lastId) {
                    lastId = m.id;
                    appendMessage(m.user, m.msg);
                }
            }
            updateStatus('Conectado', 'conn');
        } else {
            throw new Error();
        }
    } catch (err) {
        updateStatus('Erro de conexão', 'fail');
    }
}

async function sendMessage() {
    const user = document.getElementById('username').value.trim() || 'Visitante';
    const msg = document.getElementById('message').value.trim();
    if (!msg) return;
    try {
        const res = await fetch(`${SERVER_URL}/send`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user, msg })
        });
        if (res.ok) {
            document.getElementById('message').value = '';
        } else {
            throw new Error();
        }
    } catch (err) {
        appendMessage('SISTEMA', 'Falha ao enviar mensagem.');
    }
}

// Inicia o polling quando a página carregar
window.onload = () => {
    pollMessages();
    setInterval(pollMessages, 1000);
    updateStatus('Conectando...', '');
};

// Torna sendMessage global para o botão
window.sendMessage = sendMessage;