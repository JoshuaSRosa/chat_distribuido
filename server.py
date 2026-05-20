import socket
import sys
import os

PORT = int(os.environ.get('PORT', 10000))

def handle_request(data):
    # Responde com uma página HTML simples
    if b'GET / ' in data or b'GET /index.html' in data:
        body = b"""<!DOCTYPE html>
<html>
<head><title>Chat FURG - Teste</title></head>
<body>
<h1>Chat FURG - Servidor funcionando!</h1>
<p>Porta: """ + str(PORT).encode() + b"""</p>
<p>Se você está vendo isso, o servidor está rodando corretamente.</p>
</body>
</html>"""
        return b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nContent-Length: " + str(len(body)).encode() + b"\r\nConnection: close\r\n\r\n" + body
    elif b'GET /health' in data:
        body = b'{"status":"ok"}'
        return b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: " + str(len(body)).encode() + b"\r\nConnection: close\r\n\r\n" + body
    else:
        body = b'{"error":"not found"}'
        return b"HTTP/1.1 404 Not Found\r\nContent-Type: application/json\r\nContent-Length: " + str(len(body)).encode() + b"\r\nConnection: close\r\n\r\n" + body

def main():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(('0.0.0.0', PORT))
    server.listen(5)
    print(f"Servidor de teste rodando em 0.0.0.0:{PORT}", flush=True)
    sys.stdout.flush()
    while True:
        conn, addr = server.accept()
        with conn:
            data = b''
            while b'\r\n\r\n' not in data:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                data += chunk
            if data:
                response = handle_request(data)
                conn.sendall(response)

if __name__ == '__main__':
    main()