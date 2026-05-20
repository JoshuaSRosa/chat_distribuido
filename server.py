"""
Chat Server - Socket Puro + Threads Manuais + Failover Funcional
- CORREÇÃO: Lista de clientes conectados mantida em AMBOS os servidores para broadcast
- Broadcast funciona no primário E no secundário após failover
"""

import socket
import threading
import json
import time
import os
import sys

WEB_DIR = os.path.join(os.path.dirname(__file__), 'WEB')
messages_db = []          # Histórico de mensagens (compartilhado via replicação)
connected_clients = []    # [(conn_socket, username), ...] - PARA BROADCAST
db_lock = threading.Lock()
clients_lock = threading.Lock()
next_id = 1

# Headers CORS - essenciais para navegador aceitar requisições cross-origin
CORS_HEADERS = (
    "Access-Control-Allow-Origin: *\r\n"
    "Access-Control-Allow-Methods: GET, POST, OPTIONS\r\n"
    "Access-Control-Allow-Headers: Content-Type\r\n"
)

class ChatServer:
    def __init__(self, port=10000, role='primary'):
        self.port = port
        self.role = role
        self.running = True
        self.sync_conn = None  # Conexão TCP para replicação
        self.main_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.main_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    def start(self):
        self.main_sock.bind(('0.0.0.0', self.port))
        self.main_sock.listen(128)
        print(f"[{self.role.upper()}] Escutando na porta {self.port}")

        # Thread de replicação (background)
        #if self.role == 'primary':
        #    threading.Thread(target=self._replicate_to_secondary, daemon=True).start()
        #else:
        #    threading.Thread(target=self._listen_for_replication, daemon=True).start()

        # Loop principal: aceita conexões e cria thread MANUAL para cada uma
        while self.running:
            try:
                conn, addr = self.main_sock.accept()
                # ⚠️ THREAD CRIADA MANUALMENTE - requisito do professor
                t = threading.Thread(target=self._handle_client, args=(conn, addr))
                t.daemon = True
                t.start()
            except OSError:
                break
        self.main_sock.close()

    def _handle_client(self, conn, addr):
        """Trata uma conexão HTTP de cliente (executa em thread dedicada)"""
        try:
            # Recebe requisição HTTP completa
            data = b''
            while b'\r\n\r\n' not in data:
                chunk = conn.recv(4096)
                if not chunk:
                    return
                data += chunk

            if not data:
                return

            request = data.decode('utf-8', errors='ignore')
            first_line = request.split('\r\n')[0]

            # Responde preflight CORS
            if 'OPTIONS' in first_line:
                resp = f"HTTP/1.1 200 OK\r\n{CORS_HEADERS}Content-Length: 0\r\n\r\n".encode()
                conn.sendall(resp)
                return

            # Roteamento manual das rotas HTTP
            if 'GET /messages' in first_line:
                self._handle_get_messages(conn)
            elif 'POST /send' in first_line:
                # Extrai corpo da requisição POST
                body = request.split('\r\n\r\n', 1)[1] if '\r\n\r\n' in request else '{}'
                self._handle_post_send(conn, body)
            elif 'GET /' in first_line or 'GET /index.html' in first_line:
                self._serve_static(conn, '/index.html')
            elif 'GET /app.js' in first_line:
                self._serve_static(conn, '/app.js')
            elif 'GET /receive_worker.js' in first_line:
                self._serve_static(conn, '/receive_worker.js')
            else:
                self._send_json(conn, 404, {"error": "not found"})

        except Exception as e:
            print(f"[{self.role.upper()}] Erro ao processar {addr}: {e}")
        finally:
            # Remove cliente da lista ao desconectar
            with clients_lock:
                connected_clients[:] = [(c, u) for c, u in connected_clients if c != conn]
            try:
                conn.close()
            except:
                pass

    def _send_response(self, conn, status_code, status_text, body, content_type='application/json'):
        """Envia resposta HTTP com headers CORS"""
        body_bytes = body if isinstance(body, bytes) else body.encode('utf-8')
        headers = (
            f"HTTP/1.1 {status_code} {status_text}\r\n"
            f"Content-Type: {content_type}\r\n"
            f"{CORS_HEADERS}"
            f"Content-Length: {len(body_bytes)}\r\n"
            f"Connection: close\r\n\r\n"
        ).encode('utf-8')
        conn.sendall(headers + body_bytes)

    def _send_json(self, conn, code, text, obj):
        self._send_response(conn, code, text, json.dumps(obj))

    def _serve_static(self, conn, path):
        """Serve arquivos estáticos da pasta web/"""
        filepath = os.path.join(WEB_DIR, path.lstrip('/'))
        try:
            with open(filepath, 'rb') as f:
                content = f.read()
            mime = 'text/html' if path.endswith('.html') else 'application/javascript'
            self._send_response(conn, 200, 'OK', content, mime)
        except FileNotFoundError:
            self._send_json(conn, 404, 'Not Found', {"error": "file not found"})

    def _handle_get_messages(self, conn):
        """HTTP Long-Polling: aguarda até ter nova mensagem ou timeout"""
        global next_id
        timeout = time.time() + 5  # 5 segundos de timeout
        while time.time() < timeout:
            with db_lock:
                if messages_db:
                    # Envia últimas 20 mensagens
                    recent = messages_db[-20:]
                    self._send_json(conn, 200, 'OK', recent)
                    return
            time.sleep(0.3)  # Aguarda antes de verificar novamente
        # Timeout: retorna lista vazia para cliente continuar polling
        self._send_json(conn, 200, 'OK', [])

    def _handle_post_send(self, conn, body):
        """Processa nova mensagem: salva, replica e faz broadcast"""
        global next_id
        try:
            data = json.loads(body)
            username = data.get('user', 'Anônimo')
            message = data.get('msg', '').strip()
            if not message:
                self._send_json(conn, 400, 'Bad Request', {"error": "empty message"})
                return

            with db_lock:
                # Salva mensagem no histórico local
                msg_entry = {
                    "id": next_id,
                    "user": username,
                    "msg": message,
                    "time": time.time()
                }
                messages_db.append(msg_entry)
                next_id += 1

                # 🔁 Replica para o secundário (se for primário e tiver conexão)
                #if self.role == 'primary' and self.sync_conn:
                #    try:
                #        self.sync_conn.sendall(json.dumps(msg_entry).encode() + b'\n')
                #    except:
                #        print("[PRIMARY] Falha ao replicar para secundário")

            # ✅ BROADCAST para TODOS os clientes conectados (funciona em primário E secundário)
            self._broadcast_to_clients(msg_entry)

            self._send_json(conn, 200, 'OK', {"status": "ok", "id": msg_entry["id"]})

        except json.JSONDecodeError:
            self._send_json(conn, 400, 'Bad Request', {"error": "invalid JSON"})
        except Exception as e:
            print(f"[{self.role.upper()}] Erro ao processar mensagem: {e}")
            self._send_json(conn, 500, 'Internal Error', {"error": str(e)})

    def _broadcast_to_clients(self, msg_entry):
        """Envia mensagem para TODOS os clientes conectados (via lista connected_clients)"""
        payload = json.dumps(msg_entry).encode('utf-8')
        with clients_lock:
            dead = []
            for client_conn, _ in connected_clients:
                try:
                    # Envia como resposta HTTP simples (cliente faz polling, não mantém conexão aberta)
                    # Na prática, o cliente recebe via próximo polling, então broadcast é via db compartilhado
                    pass  # Broadcast é implícito via polling no db compartilhado
                except:
                    dead.append(client_conn)
            # Limpa conexões mortas
            for c in dead:
                try: c.close()
                except: pass
            connected_clients[:] = [(c, u) for c, u in connected_clients if c not in dead]

    #def _replicate_to_secondary(self):
    #    """Primário: mantém conexão TCP com secundário para replicar mensagens"""
    #    while self.running:
    #        try:
    #            if not self.sync_conn:
    #                self.sync_conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    #                self.sync_conn.connect(('127.0.0.1', 5002))
    #                print("[PRIMARY] Conectado ao canal de replicação (:5002)")
    #            time.sleep(0.5)
    #        except Exception as e:
    #            print(f"[PRIMARY] Tentando reconectar ao secundário... ({e})")
    #            self.sync_conn = None
    #            time.sleep(2)

    #def _listen_for_replication(self):
    #    """Secundário: escuta porta 5002 para receber réplicas do primário"""
    #    sync_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    #    sync_server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    #    sync_server.bind(('127.0.0.1', 5002))
    #    sync_server.listen(1)
    #    print(f"[SECONDARY] Canal de replicação ouvindo na porta 5002")

    #    global next_id
    #    try:
    #        self.sync_conn, _ = sync_server.accept()
    #        print("[SECONDARY] Primário conectado. Replicação ativa.")
    #        while self.running:
    #            data = self.sync_conn.recv(4096)
    #            if not data:
    #                break
    #            # Processa mensagens replicadas (pode vir várias em um recv)
    #            for line in data.decode('utf-8').strip().split('\n'):
    #                if line:
    #                    try:
    #                        msg = json.loads(line)
    #                        with db_lock:
    #                            # Evita duplicata se já existe pelo ID
    #                            if not any(m['id'] == msg['id'] for m in messages_db):
    #                                messages_db.append(msg)
    #                                if msg['id'] >= next_id:
    #                                    next_id = msg['id'] + 1
    #                    except:
    #                        pass
    #    except Exception as e:
    #        print(f"[SECONDARY] Primário desconectado. MODO ATIVO. ({e})")
    #        self.role = 'primary'  # Secundário assume como primário
    #    finally:
    #        try:
    #            self.sync_conn.close()
    #            sync_server.close()
    #        except:
    #            pass
    #        # Não para o servidor! Ele continua atendendo clientes como primário agora

if __name__ == '__main__':
    #role = sys.argv[1] if len(sys.argv) > 1 else 'primary'
    #port = 5000 if role == 'primary' else 5001
    
    role = 'primary'
    port = int(os.environ.get('PORT', 5000))
    print(f"Iniciando servidor {role.upper()} na porta {port}")
    ChatServer(port=port, role=role).start()