from socket import *
import socket
import threading
import time
import sys
import logging
from httpfile import HttpServer

# Global instance dari HTTP server
httpserver = HttpServer()

class ProcessTheClient(threading.Thread):
    def __init__(self, connection, address):
        self.connection = connection
        self.address = address
        threading.Thread.__init__(self)

    def run(self):
        raw_request = bytearray() # Bagus untuk data yang akumulatif seperti dibawah +=
        
        while True:
            try:
                d = self.connection.recv(1024)
                if not d:
                    break
                raw_request += d
                # Pengecekan end of header
                if b'\r\n\r\n' in raw_request:
                    break
            except OSError:
                break

        # Jika tidak ada data yang dikirimkan, close koneksi
        if not raw_request: 
            self.connection.close()
            return
            
        # Proses full request dengan httpserver instance
        full_request_string = raw_request.decode('utf-8', errors='ignore')
        try:
            logging.warning(f"data dari client: {self.address} -> {full_request_string.splitlines()[0]}") # Memotong \r\n
        except IndexError:
            logging.warning(f"data dari client: {self.address} -> (empty request)")

        hasil = httpserver.proses(full_request_string)
        
        # Kirim hasil ke client yang terhubung
        self.connection.sendall(hasil)

        # Tutup koneksi
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
    logging.basicConfig(level=logging.WARNING, format='%(asctime)s - %(levelname)s - %(message)s')
    
    svr = Server(port=8000)
    svr.start()

if __name__=="__main__":
    main()
