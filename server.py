import socket
import os
import sys

PORT = int(os.environ.get('PORT', 10000))

def handle(data):
    if b'GET / ' in data or b'GET /index.html' in data:
        body = b"""<!DOCTYPE html>
<html><head><title>Chat FURG - OK</title></head>
<body><h1>Servidor funcionando!</h1><p>Porta: """ + str(PORT).encode() + b"""</p></body></html>"""
        return b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nContent-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body
    elif b'GET /health' in data:
        body = b'{"status":"ok"}'
        return b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body
    else:
        body = b'{"error":"not found"}'
        return b"HTTP/1.1 404 Not Found\r\nContent-Type: application/json\r\nContent-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body

def main():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(('0.0.0.0', PORT))
    s.listen(5)
    print(f"✅ Servidor teste rodando em 0.0.0.0:{PORT}", flush=True)
    sys.stdout.flush()
    while True:
        conn, addr = s.accept()
        with conn:
            req = b''
            while b'\r\n\r\n' not in req:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                req += chunk
            if req:
                conn.sendall(handle(req))

if __name__ == '__main__':
    main()