// Versão definitiva - polling direto, sem Web Worker, sem complicações
(function() {
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

    async function poll() {
        try {
            const url = `${SERVER_URL}/messages?last_id=${lastId}`;
            const res = await fetch(url);
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
                throw new Error('HTTP ' + res.status);
            }
        } catch (err) {
            console.error('Poll error:', err);
            updateStatus('Falha na conexão', 'fail');
        }
    }

    window.sendMessage = async function() {
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
                document.getElementById('message').focus();
            } else {
                throw new Error();
            }
        } catch (err) {
            appendMessage('SISTEMA', 'Erro ao enviar mensagem.');
        }
    };

    // Inicia polling quando a página carregar
    window.addEventListener('load', () => {
        updateStatus('Conectando...', '');
        poll();
        setInterval(poll, 1000);
    });
})();