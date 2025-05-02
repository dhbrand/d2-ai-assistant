import http.server
import socketserver

PORT = 4200

class TestHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        print(f"Received request: {self.path}")
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(b"Test server is working!")

with socketserver.TCPServer(("localhost", PORT), TestHandler) as httpd:
    print(f"Serving at port {PORT}")
    httpd.serve_forever() 