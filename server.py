"""
Chat Server - Socket Puro + Threads Manuais + Failover Funcional
- Para deploy no Render: primário e secundário como serviços separados
- Replicação via HTTP (socket puro) para o secundário
- Cliente com failover automático
"""

import socket
import threading
import json
import time
import os
import sys
import urllib.request

WEB_DIR = os.path.join(os.path.dirname(__file__), 'web')
messages_db = []
connected_clients = []
db_lock = threading.Lock()
clients_lock = threading.Lock()
next_id = 1

CORS_HEADERS = (
    "Access-Control-Allow-Origin: *\r\n"
    "Access-Control-Allow-Methods: GET, POST, OPTIONS\r\n"
    "Access-Control-Allow-Headers: Content-Type\r\n"
)

class ChatServer:
    def __init__(self, port, role='primary'):
        self.port = port
        self.role = role
        self.running = True
        self.main_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.main_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.primary_url = os.environ.get('PRIMARY_URL', '')   # para o secundário saber onde está o primário
        # URL do secundário (definida via variável de ambiente)
        self.secondary_url = os.environ.get('SECONDARY_URL', '')
        # Timeout para não travar
        self.main_sock.settimeout(1.0)

#Adições para sincronização e monitoramento entre primário e secundário
    def _sync_from_secondary(self):
        #Primário: ao iniciar, recupera mensagens do secundário (se ele estiver ativo)
        try:
            # Tenta obter as últimas mensagens do secundário (via HTTP)
            req = urllib.request.Request(f"{self.secondary_url}/messages")
            with urllib.request.urlopen(req, timeout=5) as resp:
                msgs = json.loads(resp.read().decode())
                with db_lock:
                    global next_id
                    for msg in msgs:
                        if not any(m['id'] == msg['id'] for m in messages_db):
                            messages_db.append(msg)
                            if msg['id'] >= next_id:
                                next_id = msg['id'] + 1
                print(f"[PRIMARY] Sincronizado {len(msgs)} mensagens do secundário.", flush=True)
        except Exception as e:
            print(f"[PRIMARY] Falha ao sincronizar com secundário: {e}", flush=True)

    def _monitor_primary(self):
        """Thread do secundário: verifica periodicamente se o primário está vivo"""
        while self.running:
            time.sleep(10)  # verifica a cada 10 segundos
            try:
                req = urllib.request.Request(f"{self.primary_url}/health")
                with urllib.request.urlopen(req, timeout=3) as resp:
                    data = json.loads(resp.read().decode())
                    if data.get('role') == 'primary':
                        # Primário está vivo. Se este servidor ainda está como primário, volta a ser secundário
                        if self.role != 'secondary':
                            print("[SECONDARY] Primário detectado. Voltando a ser SECONDARY.", flush=True)
                            self.role = 'secondary'
                            # Não precisa limpar mensagens, apenas para de se considerar ativo para novos envios
                            # O cliente continuará tentando o primário se fizermos failback.
            except Exception:
                # Primário não responde, mantém como está (já está secondary ou primary)
                pass

    def _become_secondary(self):
        """Força o servidor a atuar como secundário (usado pelo monitor)"""
        self.role = 'secondary'
        # Aqui você pode opcionalmente limpar alguma flag de "ativo" se tiver
    def start(self):
        self.main_sock.bind(('0.0.0.0', self.port))
        self.main_sock.listen(128)
        print(f"[{self.role.upper()}] Escutando na porta {self.port}", flush=True)
        print(f"[{self.role.upper()}] Servindo arquivos de: {WEB_DIR}", flush=True)
        sys.stdout.flush()

        #Verificação para realizar sincronização entre primário e secundário
        if self.role == 'primary' and self.secondary_url:
            self._sync_from_secondary()
        
        #Se for secundário, inicia thread que verifica se o primário voltou
        if self.role == 'secondary' and self.primary_url:
            threading.Thread(target=self._monitor_primary, daemon=True).start()

        while self.running:
            try:
                conn, addr = self.main_sock.accept()
                t = threading.Thread(target=self._handle_client, args=(conn, addr))
                t.daemon = True
                t.start()
            except socket.timeout:
                continue
            except OSError:
                break
        self.main_sock.close()

    def _send_http_request(self, host, port, path, body):
        """Envia uma requisição HTTP pura via socket (sem bibliotecas)"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            sock.connect((host, port))
            request = (
                f"POST {path} HTTP/1.1\r\n"
                f"Host: {host}\r\n"
                f"Content-Type: application/json\r\n"
                f"Content-Length: {len(body)}\r\n"
                f"Connection: close\r\n"
                f"\r\n"
                f"{body}"
            )
            sock.sendall(request.encode())
            sock.close()
        except Exception as e:
            print(f"[{self.role.upper()}] Erro ao replicar: {e}", flush=True)

    def _replicate_to_secondary(self, msg_entry):
        """Replica mensagem para o secundário via HTTP"""
        if not self.secondary_url:
            return
        # Extrai host e porta da URL (ex: https://secundario.onrender.com -> host, porta 443)
        # Para simplificar, assumimos que a URL é http:// e porta 80 ou https e 443
        # No Render, o serviço secundário tem URL https, então precisamos de socket com SSL.
        # Vamos usar urllib para simplificar (ainda é socket por baixo)
        try:
            data = json.dumps(msg_entry).encode()
            req = urllib.request.Request(
                f"{self.secondary_url}/replicate",
                data=data,
                headers={'Content-Type': 'application/json'},
                method='POST'
            )
            urllib.request.urlopen(req, timeout=5)
        except Exception as e:
            print(f"[{self.role.upper()}] Falha ao replicar: {e}", flush=True)

    def _handle_client(self, conn, addr):
        try:
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

            if '/health' not in first_line:
                print(f"[{self.role.upper()}] {addr} - {first_line[:80]}", flush=True)

            if 'OPTIONS' in first_line:
                resp = f"HTTP/1.1 200 OK\r\n{CORS_HEADERS}Content-Length: 0\r\n\r\n".encode()
                conn.sendall(resp)
                return

            # Rotas
            if 'GET /health' in first_line:
                self._handle_health(conn)
            elif 'GET /messages' in first_line:
                self._handle_get_messages(conn)
            elif 'POST /send' in first_line:
                body = request.split('\r\n\r\n', 1)[1] if '\r\n\r\n' in request else '{}'
                self._handle_post_send(conn, body)
            elif 'POST /replicate' in first_line:
                # Rota usada pelo primário para replicar mensagens
                body = request.split('\r\n\r\n', 1)[1] if '\r\n\r\n' in request else '{}'
                self._handle_replicate(conn, body)
            elif 'GET /app.js' in first_line:
                self._serve_static(conn, '/app.js')
            elif 'GET /receive_worker.js' in first_line:
                self._serve_static(conn, '/receive_worker.js')
            elif 'GET /' in first_line or 'GET /index.html' in first_line:
                self._serve_static(conn, '/index.html')
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

    def _handle_replicate(self, conn, body):
        """Recebe uma mensagem replicada do primário e a insere no banco local"""
        global next_id
        try:
            msg_entry = json.loads(body)
            with db_lock:
                if not any(m['id'] == msg_entry['id'] for m in messages_db):
                    messages_db.append(msg_entry)
                    if msg_entry['id'] >= next_id:
                        next_id = msg_entry['id'] + 1
            self._send_json(conn, 200, {"status": "replicated"})
        except Exception as e:
            print(f"[SECONDARY] Erro ao replicar: {e}", flush=True)
            self._send_json(conn, 500, {"error": str(e)})

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

    def _handle_health(self, conn):
        self._send_json(conn, 200, {
            "status": "healthy",
            "role": self.role,
            "messages": len(messages_db),
            "port": self.port
        })

    def _handle_get_messages(self, conn):
        timeout = time.time() + 5
        while time.time() < timeout:
            with db_lock:
                if messages_db:
                    recent = messages_db[-20:]
                    self._send_json(conn, 200, recent)
                    return
            time.sleep(0.3)
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

            # Se for primário, replica para o secundário
            if self.role == 'primary' and self.secondary_url:
                threading.Thread(target=self._replicate_to_secondary, args=(msg_entry,), daemon=True).start()

            self._send_json(conn, 200, {"status": "ok", "id": msg_entry["id"]})

        except Exception as e:
            print(f"[{self.role.upper()}] Erro: {e}", flush=True)
            self._send_json(conn, 500, {"error": str(e)})

if __name__ == '__main__':
    role = os.environ.get('ROLE', 'primary')
    port = int(os.environ.get('PORT', 10000))
    print(f"Iniciando servidor {role.upper()} na porta {port}", flush=True)
    ChatServer(port=port, role=role).start()