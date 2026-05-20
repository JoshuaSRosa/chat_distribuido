// Web Worker dedicado à recepção (thread manual equivalente em JS)
let config = { url: '', lastId: 0, active: true };

self.onmessage = (e) => {
    if (e.data.fail) {
        // Sinaliza para o app.js que deve trocar de servidor
        self.postMessage({ switch: true });
        return;
    }
    if (e.data.url) {
        config.url = e.data.url;
        config.active = true;
        config.lastId = e.data.lastId || 0;
        poll();
    }
    if (e.data.stop) config.active = false;
};

async function poll() {
    while (config.active && config.url) {
        try {
            const response = await fetch(`${config.url}/messages?last_id=${config.lastId}`, {
                method: 'GET',
                headers: { 'Accept': 'application/json' }
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            // ✅ Conexão bem-sucedida: avisa que está "Conectado"
            self.postMessage({ status: 'Conectado', cls: 'conn' });

            const messages = await response.json();
            if (Array.isArray(messages) && messages.length > 0) {
                for (const msg of messages) {
                    if (msg.id > config.lastId) {
                        config.lastId = msg.id;
                        self.postMessage({
                            type: 'message',
                            user: msg.user,
                            msg: msg.msg,
                            time: msg.time
                        });
                    }
                }
            }
        } catch (error) {
            // ❌ Falha na conexão: avisa que está "Fora" e tenta novamente
            self.postMessage({ status: 'Servidor fora. Aguardando...', cls: 'fail' });
            await sleep(1500);
            continue;
        }
        await sleep(800); // Intervalo entre polls
    }
}

function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}