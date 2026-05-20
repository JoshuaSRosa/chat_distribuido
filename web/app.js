(function() {
    // URLs definidas no HTML (window.PRIMARY_URL e window.BACKUP_URL)
    const PRIMARY_URL = window.PRIMARY_URL || `http://${location.hostname}:5000`;
    const BACKUP_URL = window.BACKUP_URL || `http://${location.hostname}:5001`;
    let currentServer = PRIMARY_URL;
    let lastId = 0;
    let pollingInterval = null;

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

    // Função que tenta uma requisição com fallback para o outro servidor
    async function fetchWithFailover(url, options) {
        try {
            const res = await fetch(url, options);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            return res;
        } catch (err) {
            console.warn(`Falha no servidor ${currentServer}, tentando backup...`);
            // Troca para o servidor backup
            currentServer = (currentServer === PRIMARY_URL) ? BACKUP_URL : PRIMARY_URL;
            updateStatus(`Tentando ${currentServer === PRIMARY_URL ? 'primário' : 'backup'}...`, 'fail');
            // Tenta novamente com o novo servidor
            const newUrl = url.replace(/^https?:\/\/[^\/]+/, currentServer);
            const res = await fetch(newUrl, options);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            return res;
        }
    }

    async function poll() {
        try {
            const url = `${currentServer}/messages?last_id=${lastId}`;
            const res = await fetchWithFailover(url, { method: 'GET', headers: { 'Accept': 'application/json' } });
            const msgs = await res.json();
            for (const m of msgs) {
                if (m.id > lastId) {
                    lastId = m.id;
                    appendMessage(m.user, m.msg);
                }
            }
            updateStatus(`Conectado (${currentServer === PRIMARY_URL ? 'primário' : 'backup'})`, 'conn');
        } catch (err) {
            console.error('Poll error:', err);
            updateStatus('Falha na conexão', 'fail');
        }
    }
    
    //Lógica de failback
    let failbackInterval = null;

    function tryFailback() {
        if (currentServer === PRIMARY_URL) return; // já no primário
        fetch(`${PRIMARY_URL}/health`)
            .then(res => res.ok ? res.json() : Promise.reject())
            .then(data => {
                if (data.status === 'healthy') {
                    console.log('Primário recuperado, voltando...');
                    currentServer = PRIMARY_URL;
                    updateStatus('Conectado (primário)', 'conn');
                    // Opcional: recarregar mensagens para garantir sincronia
                    lastId = 0;
                    poll(); // força uma nova poll
                }
            })
            .catch(() => {});
    }

    // Inicie o failback quando a página carregar (dentro do load event)
    window.addEventListener('load', () => {
        // ... código existente ...
        if (failbackInterval) clearInterval(failbackInterval);
        failbackInterval = setInterval(tryFailback, 15000); // tenta a cada 15s
    });

    window.sendMessage = async function() {
        const user = document.getElementById('username').value.trim() || 'Visitante';
        const msg = document.getElementById('message').value.trim();
        if (!msg) return;
        try {
            const url = `${currentServer}/send`;
            const res = await fetchWithFailover(url, {
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

    window.addEventListener('load', () => {
        updateStatus('Conectando...', '');
        poll();
        if (pollingInterval) clearInterval(pollingInterval);
        pollingInterval = setInterval(poll, 1000);
    });
})();