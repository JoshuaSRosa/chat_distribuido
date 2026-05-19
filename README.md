# Chat FURG - Sistema Distribuído com Tolerância a Falhas

## Descrição
Sistema de chat em tempo real com arquitetura primário-secundário. Desenvolvido em Python puro com gerenciamento explícito de threads e failover automático no cliente.

## Arquitetura
- Servidor Primário (Porta 5000): Atende clientes, gerencia threads manualmente, replica mensagens para o secundário.
- Servidor Secundário (Porta 5001): Em standby, sincroniza estado via canal TCP dedicado. Assume automaticamente se o primário cair.
- Cliente Web: Interface leve com `Web Worker` dedicado à recepção (simula thread de recebimento). Implementa failover transparente via polling.

## Como Executar
1. Abra 3 terminais.
2. Terminal 1: cd caminho/para/chat_resiliente
   Terminal 1: `python server.py primary`
     Esperado: [PRIMARY] Escutando na porta 5000
3. Terminal 2: cd caminho/para/chat_furg
   Terminal 2:`python server.py secondary`
     Esperado: [SECONDARY] Escutando na porta 5001 e [SECONDARY] Canal de replicação ouvindo na 5002
4. Terminal 3: cd caminho/para/chat_furg
   Terminal 3: `python -m http.server 8080 --directory web`
     Esperado: Serving HTTP on 0.0.0.0 port 8080...
5. Acesse `http://localhost:8080` em dois navegadores (ou abas).
6. Para testar falha:aperte ou pressione F12 no nagador em seguida dê `Ctrl+C` no terminal do primário. O cliente reconectará automaticamente ao secundário sem perder a conversa.

## Requisitos
- Python 3.8+
- Navegador moderno
- Sistema: Linux/Windows/macOS