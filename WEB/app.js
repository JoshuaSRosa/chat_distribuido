/*
const PRIMARY_URL = `http://${location.hostname}:5000`;
const BACKUP_URL = `http://${location.hostname}:5001`;
let currentServer = PRIMARY_URL;
let worker = null;
*/
const SERVER_URL = window.location.origin;
let pollInterval = null;
let lasted = 0;

/*
// Inicia o Web Worker de recepção
function startWorker(url) {
    if (worker) worker.terminate();
    worker = new Worker('receive_worker.js');

    worker.onmessage = (e) => {
        if (e.data.status) updateStatus(e.data.status, e.data.cls);
        if (e.data.type === 'message') appendMessage(e.data.user, e.data.msg);
        if (e.data.switch) {
            console.warn('🔄 Failover: migrando para backup');
            currentServer = BACKUP_URL;
            setTimeout(() => startWorker(currentServer), 500);
        }
    };

    worker.postMessage({ url: url });
}
*/

function updateStatus(text, cls) {
    const el = document.getElementById('status');
    if (el) {
        el.textContent = `Status: ${text}`;
        el.className = cls || '';
    }
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

// NOVA FUNÇÃO: Polling simples sem Web Worker
async function pollMessages() {
    try {
        const response = await fetch(`${SERVER_URL}/messages?last_id=${lastId}`);
        
        if (response.ok) {
            const messages = await response.json();
            
            if (messages && messages.length > 0) {
                for (const msg of messages) {
                    if (msg.id > lastId) {
                        lastId = msg.id;
                        appendMessage(msg.user, msg.msg);
                    }
                }
            }
            
            updateStatus('Conectado ao servidor', 'conn');
        } else {
            throw new Error(`HTTP ${response.status}`);
        }
    } catch (error) {
        console.error('Erro no polling:', error);
        updateStatus('Erro de conexão. Tentando reconectar...', 'fail');
    }
}

//  Função GLOBAL (chamada pelo onclick e onkeydown do HTML)
function sendMessage() {
    const userEl = document.getElementById('username');
    const msgEl = document.getElementById('message');
    const username = userEl.value.trim() || 'Visitante';
    const message = msgEl.value.trim();

    if (!message) return;

    console.log(`📤 Enviando para ${currentServer}: "${message}"`);

    fetch(`${SERVER_URL}/send`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user: username, msg: message })
    })
        .then(res => {
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            return res.json();
        })
        .then(data => {
            console.log('✅ Sucesso:', data);
            msgEl.value = '';
            msgEl.focus();
        })
        .catch(err => {
            console.error('❌ Falha ao enviar:', err);
            //if (worker) worker.postMessage({ fail: true });
        });
}

// Inicia ao carregar a página
window.onload = () => {
    //startWorker(currentServer);
    //updateStatus('Conectado ao servidor primário', 'conn');
    pollMessages();
    setInterval(pollMessages,1000);
    updateStatus('Conectandoao servidor...','');
};
window.sendMessage = sendMessage;