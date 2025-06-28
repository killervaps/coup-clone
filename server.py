import socket
import threading
import logging
from httpfile import HttpServer # Import the new http.py

# Global instance of the HTTP server logic
httpserver = HttpServer()

class ProcessTheClient(threading.Thread):
    def __init__(self, connection, address):
        self.connection = connection
        self.address = address
        threading.Thread.__init__(self)

    def run(self):
        # A more robust way to receive HTTP requests
        raw_request = bytearray()
        # First, read headers
        while True:
            try:
                d = self.connection.recv(1024)
                if not d:
                    break
                raw_request += d
                # A simple check for end of headers. For POST, we might need more.
                if b'\r\n\r\n' in raw_request:
                    break
            except OSError:
                break

        # Decode and process if we received anything
        if not raw_request:
            self.connection.close()
            return
            
        request_string = raw_request.decode('utf-8', errors='ignore')

        # Check for Content-Length to read the full body correctly for POST requests
        headers = request_string.split('\r\n')
        content_length = 0
        for h in headers:
            if h.lower().startswith('content-length:'):
                try:
                    content_length = int(h.split(':')[1].strip())
                    break
                except (ValueError, IndexError):
                    pass
        
        # Ensure the full body has been received
        header_end = request_string.find('\r\n\r\n')
        if header_end != -1:
            body_part_bytes = raw_request[header_end+4:]
            while len(body_part_bytes) < content_length:
                 try:
                    d = self.connection.recv(1024)
                    if not d:
                        break
                    raw_request += d
                    body_part_bytes += d
                 except OSError:
                    break
        
        # Process the full request using the imported httpserver instance
        full_request_string = raw_request.decode('utf-8', errors='ignore')
        try:
            logging.warning(f"data dari client: {self.address} -> {full_request_string.splitlines()[0]}")
        except IndexError:
            logging.warning(f"data dari client: {self.address} -> (empty request)")

        hasil = httpserver.proses(full_request_string)
        
        self.connection.sendall(hasil)
        self.connection.close()

class Server(threading.Thread):
    def __init__(self, port=8000):
        self.the_clients = []
        self.my_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.my_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.port = port
        threading.Thread.__init__(self)

    def run(self):
        self.my_socket.bind(('0.0.0.0', self.port))
        self.my_socket.listen(1)
        logging.warning(f"Coup server started on port {self.port}")
        while True:
            try:
                self.connection, self.client_address = self.my_socket.accept()
                logging.warning("connection from {}".format(self.client_address))

                clt = ProcessTheClient(self.connection, self.client_address)
                clt.start()
                self.the_clients.append(clt)
            except Exception as e:
                logging.error(f"Error accepting connection: {e}")

def main():
    # Setup basic logging
    logging.basicConfig(level=logging.WARNING, format='%(asctime)s - %(levelname)s - %(message)s')
    
    # Use port 8000 to match the client
    svr = Server(port=8000)
    svr.start()

if __name__=="__main__":
    main()
