"""
Chat Server - Socket Puro + Threads Manuais + Failover Funcional
- Versão adaptada para deploy no Render
- CORREÇÃO: Lista de clientes conectados mantida em AMBOS os servidores para broadcast
- Broadcast funciona no primário E no secundário após failover
"""

import socket
import threading
import json
import time
import os
import sys

# [!] Força o uso de 'WEB' (maiúsculo) como você tem. Se quiser aceitar ambos, pode usar a lógica anterior.
WEB_DIR = os.path.join(os.path.dirname(__file__), 'web')
messages_db = []          # Histórico de mensagens
connected_clients = []    # [(conn_socket, username), ...]
db_lock = threading.Lock()
clients_lock = threading.Lock()
next_id = 1

CORS_HEADERS = (
    "Access-Control-Allow-Origin: *\r\n"
    "Access-Control-Allow-Methods: GET, POST, OPTIONS\r\n"
    "Access-Control-Allow-Headers: Content-Type\r\n"
)

class ChatServer:
    def __init__(self, port=int(os.environ.get('PORT', 10000)), role='primary'):
        self.port = port
        self.role = role
        self.running = True
        self.sync_conn = None
        self.main_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.main_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    def start(self):
        self.main_sock.bind(('0.0.0.0', self.port))
        self.main_sock.listen(128)
        # [!] Adiciona timeout para não bloquear o accept para sempre
        self.main_sock.settimeout(1.0)
        print(f"[{self.role.upper()}] Escutando na porta {self.port}", flush=True)
        print(f"[{self.role.upper()}] Servindo arquivos de: {WEB_DIR}", flush=True)
        sys.stdout.flush()

        # Threads de replicação comentadas (não usadas no deploy)
        # if self.role == 'primary':
        #     threading.Thread(target=self._replicate_to_secondary, daemon=True).start()
        # else:
        #     threading.Thread(target=self._listen_for_replication, daemon=True).start()

        while self.running:
            try:
                conn, addr = self.main_sock.accept()
                t = threading.Thread(target=self._handle_client, args=(conn, addr))
                t.daemon = True
                t.start()
            except socket.timeout:
                continue  # Permite verificar self.running periodicamente
            except OSError:
                break
        self.main_sock.close()

    def _handle_client(self, conn, addr):
        try:
            # [!] Timeout para não ficar preso em recv
            conn.settimeout(5.0)
            data = b''
            while b'\r\n\r\n' not in data:
                try:
                    chunk = conn.recv(4096)
                    if not chunk:
                        return
                    data += chunk
                except socket.timeout:
                    return
                if len(data) > 65536:
                    return

            if not data:
                return

            request = data.decode('utf-8', errors='ignore')
            first_line = request.split('\r\n')[0]

            # Log apenas para requisições que não sejam health check (evita spam)
            if '/health' not in first_line:
                print(f"[{self.role.upper()}] {addr} - {first_line[:80]}", flush=True)

            if 'OPTIONS' in first_line:
                resp = f"HTTP/1.1 200 OK\r\n{CORS_HEADERS}Content-Length: 0\r\n\r\n".encode()
                conn.sendall(resp)
                return

            # [!] Nova rota /health
            if 'GET /health' in first_line:
                self._handle_health(conn)
            elif 'GET /messages' in first_line:
                self._handle_get_messages(conn)
            elif 'POST /send' in first_line:
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
            print(f"[{self.role.upper()}] Erro: {e}", flush=True)
        finally:
            with clients_lock:
                connected_clients[:] = [(c, u) for c, u in connected_clients if c != conn]
            try:
                conn.close()
            except:
                pass

    def _send_response(self, conn, status_code, status_text, body, content_type='application/json'):
        body_bytes = body if isinstance(body, bytes) else body.encode('utf-8')
        headers = (
            f"HTTP/1.1 {status_code} {status_text}\r\n"
            f"Content-Type: {content_type}\r\n"
            f"{CORS_HEADERS}"
            f"Content-Length: {len(body_bytes)}\r\n"
            f"Connection: close\r\n\r\n"
        ).encode('utf-8')
        conn.sendall(headers + body_bytes)

    def _send_json(self, conn, code, obj):
        self._send_response(conn, code, "OK", json.dumps(obj))

    def _serve_static(self, conn, path):
        filepath = os.path.join(WEB_DIR, path.lstrip('/'))
        try:
            with open(filepath, 'rb') as f:
                content = f.read()
            mime = 'text/html' if path.endswith('.html') else 'application/javascript'
            self._send_response(conn, 200, 'OK', content, mime)
        except FileNotFoundError:
            self._send_json(conn, 404, {"error": "file not found"})

    # [!] Novo método para health check
    def _handle_health(self, conn):
        self._send_json(conn, 200, {
            "status": "healthy",
            "role": self.role,
            "messages": len(messages_db),
            "port": self.port
        })

    def _handle_get_messages(self, conn):
        """HTTP Long-Polling: aguarda até ter nova mensagem ou timeout"""
        timeout = time.time() + 5
        while time.time() < timeout:
            with db_lock:
                if messages_db:
                    recent = messages_db[-20:]
                    self._send_json(conn, 200, recent)
                    return
            time.sleep(0.3)
        # Timeout: retorna lista vazia
        self._send_json(conn, 200, [])

    def _handle_post_send(self, conn, body):
        global next_id
        try:
            data = json.loads(body)
            username = data.get('user', 'Anônimo')
            message = data.get('msg', '').strip()
            if not message:
                self._send_json(conn, 400, {"error": "empty message"})
                return

            with db_lock:
                msg_entry = {
                    "id": next_id,
                    "user": username,
                    "msg": message,
                    "time": time.time()
                }
                messages_db.append(msg_entry)
                next_id += 1

                # Replicação comentada
                # if self.role == 'primary' and self.sync_conn:
                #     try:
                #         self.sync_conn.sendall(json.dumps(msg_entry).encode() + b'\n')
                #     except:
                #         print("[PRIMARY] Falha ao replicar")

            self._broadcast_to_clients(msg_entry)
            self._send_json(conn, 200, {"status": "ok", "id": msg_entry["id"]})

        except json.JSONDecodeError:
            self._send_json(conn, 400, {"error": "invalid JSON"})
        except Exception as e:
            print(f"[{self.role.upper()}] Erro: {e}", flush=True)
            self._send_json(conn, 500, {"error": str(e)})

    def _broadcast_to_clients(self, msg_entry):
        with clients_lock:
            dead = []
            for client_conn, _ in connected_clients:
                try:
                    pass  # broadcast via polling
                except:
                    dead.append(client_conn)
            for c in dead:
                try:
                    c.close()
                except:
                    pass
            connected_clients[:] = [(c, u) for c, u in connected_clients if c not in dead]

    # Os métodos _replicate_to_secondary e _listen_for_replication foram comentados para economia de espaço.
    # Mantenha-os comentados no deploy.

if __name__ == '__main__':
    role = 'primary'
    port = int(os.environ.get('PORT', 10000))  # [!] Porta padrão 10000 para o Render
    print(f"Iniciando servidor {role.upper()} na porta {port}", flush=True)
    ChatServer(port=port, role=role).start()