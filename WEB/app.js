// app.js - Versão simplificada para deploy no Render
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
        const response = await fetch(`${SERVER_URL}/messages?last_id=${lastId}`);
        if (response.ok) {
            const messages = await response.json();
            for (const msg of messages) {
                if (msg.id > lastId) {
                    lastId = msg.id;
                    appendMessage(msg.user, msg.msg);
                }
            }
            updateStatus('Conectado', 'conn');
        } else {
            throw new Error(`HTTP ${response.status}`);
        }
    } catch (error) {
        console.error('Polling error:', error);
        updateStatus('Erro de conexão', 'fail');
    }
}

async function sendMessage() {
    const userEl = document.getElementById('username');
    const msgEl = document.getElementById('message');
    const username = userEl.value.trim() || 'Visitante';
    const message = msgEl.value.trim();
    if (!message) return;

    try {
        const response = await fetch(`${SERVER_URL}/send`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user: username, msg: message })
        });
        if (response.ok) {
            msgEl.value = '';
            msgEl.focus();
        } else {
            throw new Error();
        }
    } catch (error) {
        appendMessage('SISTEMA', 'Erro ao enviar mensagem.');
    }
}

window.onload = () => {
    pollMessages();
    setInterval(pollMessages, 1000); // Polling a cada segundo
    updateStatus('Conectando...', '');
};

window.sendMessage = sendMessage;