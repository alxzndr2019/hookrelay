import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("content-length", 0))
        body = self.rfile.read(length).decode()
        print(f"\n--- {self.path} ---")
        for k, v in self.headers.items():
            print(f"{k}: {v}")
        print(body)

        if self.path == "/slow":
            time.sleep(30)
        status = 500 if self.path == "/fail" else 200
        self.send_response(status)
        self.end_headers()
        self.wfile.write(b"ok" if status == 200 else b"boom")


ThreadingHTTPServer(("127.0.0.1", 9000), Handler).serve_forever()