from socket import *
import socket
import time
import sys
import logging
import multiprocessing
from concurrent.futures import ProcessPoolExecutor

class BackendList:
	def __init__(self):
		self.servers=[]
		self.client_map = {}
		self.servers.append({'host': '127.0.0.1', 'port': 8000, 'counter': 0})
		self.servers.append({'host': '127.0.0.1', 'port': 8001, 'counter': 0})
		self.servers.append({'host': '127.0.0.1', 'port': 8002, 'counter': 0})
		self.current = 0

	def getserver(self, client_ip):
		logging.warning(f"new client connected from {client_ip}")
		
		if client_ip in self.client_map: # Jika suatu ip client pernah connect ke server sebelumnya
			s = self.client_map.get(client_ip)
		
		else: # Jika suatu ip client belum pernah connect ke server sebelumnya
			s = (self.servers[self.current]['host'], self.servers[self.current]['port'])
			self.servers[self.current]['counter'] = self.servers[self.current]['counter'] + 1
			self.client_map[client_ip] = s

			if self.servers[self.current]['counter'] == 4: # Jika suatu backend server mencapai maksimum player
				self.current = self.current + 1

			if self.current >= len(self.servers): # Jika seluruh backend server telah digunakan
				self.current = 0
				for server in self.servers:
					server['counter'] = 0

		return s

def ProcessTheClient(connection, address, backend_sock, mode='toupstream'):
	try:
		while True:
			try:
				if (mode == 'toupstream'):
					datafrom_client = connection.recv(8192)
					if datafrom_client:
							backend_sock.sendall(datafrom_client)
					else:
							backend_sock.close()
							break
				elif (mode == 'toclient'):
					datafrom_backend = backend_sock.recv(8192)

					if datafrom_backend:
						connection.sendall(datafrom_backend)
					else:
						connection.close()
						break
			except OSError as e:
				pass
	except Exception as ee:
		logging.warning(f"error {str(ee)}")
	connection.close()
	return

def Server():
	the_clients = []
	my_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
	my_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
	backend = BackendList()

	my_socket.bind(('0.0.0.0', 8003))
	my_socket.listen(1)

	logging.warning(f"Load balancer started on port 8003")

	with ProcessPoolExecutor(20) as executor:
		while True:
			connection, client_address = my_socket.accept()
			client_ip = client_address[0]
			backend_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
			backend_sock.settimeout(1)
			backend_address = backend.getserver(client_ip)
			logging.warning(f"{client_address} connecting to {backend_address}")
			try:
				backend_sock.connect(backend_address)

				executor.submit(ProcessTheClient, connection, client_address,backend_sock,'toupstream')
				
				executor.submit(ProcessTheClient, connection, client_address,backend_sock,'toclient')
				
			except Exception as err:
				logging.error(err)
				pass

def main():
	Server()

if __name__=="__main__":
	main()