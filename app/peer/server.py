import socket
import threading
import json
from typing import Dict
from app.database.db import Database
from app.utils.helpers import log_event
from app.config import Config

class PeerServer:
    def __init__(self, ip: str, port: int, peer_id: str):
        self.ip = ip
        self.port = port
        self.peer_id = peer_id
        self.server_socket = None
        self.is_running = False
        self._lock = threading.Lock()
        self.db = Database()

    def run_peer_server(self):
        """Start peer server to handle piece requests"""
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.bind((self.ip, self.port))
            self.server_socket.listen(5)
            self.is_running = True
            
            log_event("SERVER", f"Peer server running on {self.ip}:{self.port}", "info")
            
            while self.is_running:
                client_socket, addr = self.server_socket.accept()
                # Handle each client in a new thread
                thread = threading.Thread(
                    target=self._handle_client_request,
                    args=(client_socket, addr)
                )
                thread.start()
                
        except Exception as e:
            log_event("ERROR", f"Peer server error: {e}", "error")
        finally:
            if self.server_socket:
                self.server_socket.close()

    def _handle_client_request(self, client_socket: socket.socket, addr: tuple):
        """Handle incoming piece requests"""
        try:
            # Receive request
            data = client_socket.recv(1024).decode()
            request = eval(data)  # Convert string to dict
            
            if request['type'] == 'request_piece':
                self.send_piece_data(
                    request['piece_index'],
                    client_socket,
                    request['peer_id'],
                    request['metainfo_id']
                )
                
        except Exception as e:
            log_event("ERROR", f"Error handling client request: {e}", "error")
        finally:
            client_socket.close()

    def send_piece_data(self, piece_index: int, client_socket: socket.socket, 
                       peer_id: str, metainfo_id: str):
        """Send requested piece data to peer"""
        try:
            # Get piece data from database
            peer = self.db.get_peer(self.peer_id)
            if not peer:
                return

            piece_data = None
            for piece_info in peer['piece_info']:
                if (piece_info['metainfo_id'] == metainfo_id and 
                    piece_info['index'] == piece_index):
                    piece_data = piece_info['piece']
                    break

            if piece_data:
                client_socket.sendall(piece_data)
                # Update peer stats
                self._update_peer_stats(len(piece_data), True)
                log_event("PIECE", f"Sent piece {piece_index} to peer {peer_id}", "success")
            else:
                log_event("ERROR", f"Piece {piece_index} not found", "error")
                self._update_peer_stats(0, False)

        except Exception as e:
            log_event("ERROR", f"Error sending piece data: {e}", "error")
            self._update_peer_stats(0, False)

    def _update_peer_stats(self, bytes_sent: int, success: bool):
        """Update peer statistics"""
        peer = self.db.get_peer(self.peer_id)
        if peer:
            if success:
                peer['successful_uploads'] += 1
                peer['total_uploaded'] += bytes_sent
            else:
                peer['failed_uploads'] += 1
            
            total_attempts = peer['successful_uploads'] + peer['failed_uploads']
            peer['network_stats']['success_rate'] = (
                peer['successful_uploads'] / total_attempts if total_attempts > 0 else 1.0
            )
            
            self.db.update_peer_stats(self.peer_id, peer['network_stats'])