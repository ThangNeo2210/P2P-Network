from typing import List, Dict, Optional
import hashlib
from app.database.db import Database
from app.utils.helpers import log_event
from app.config import Config
import socket
import threading
import json
import time
import bencodepy
import os

class Tracker:
    def __init__(self):
        self.db = Database()
        self.server_socket = None
        self.is_running = False
        self._lock = threading.Lock()
        self.connected_peers = {}  # Store active peer connections

    def get_all_peer_info(self) -> List[Dict]:
        """Get all registered peers"""
        try:
            peers = self.db.peers.all()
            return [
                {
                    'peer_id': peer['peer_id'],
                    'ip_address': peer['ip_address'],
                    'port': peer['port'],
                    'piece_info': peer['piece_info']
                }
                for peer in peers
            ]
        except Exception as e:
            log_event("ERROR", f"Error getting peer info: {e}", "error")
            return []

    def get_peer(self, name: str) -> Optional[Dict]:
        """Get specific peer by name/id"""
        try:
            peer = self.db.get_peer(name)
            if peer:
                return {
                    'peer_id': peer['peer_id'],
                    'ip_address': peer['ip_address'],
                    'port': peer['port'],
                    'piece_info': peer['piece_info']
                }
            return None
        except Exception as e:
            log_event("ERROR", f"Error getting peer {name}: {e}", "error")
            return None

    def upload_file(self, file_path: str, peer_id: str) -> bool:
        """Upload file and update peer piece info"""
        try:
            from app.torrent.piece import generate_pieces
            pieces = generate_pieces(file_path, Config.PIECE_LENGTH)
            
            file_name = os.path.basename(file_path)
            file_length = os.path.getsize(file_path)
            
            # Create torrent entry
            info_hash = self._generate_info_hash(file_name, pieces, file_length)
            
            torrent_data = {
                'info_hash': info_hash,
                'info': {
                    'name': file_name,
                    'piece_length': Config.PIECE_LENGTH,
                    'length': file_length,
                    'pieces': pieces
                }
            }
            self.db.add_torrent(torrent_data)

            # Create file entry
            file_data = {
                'file_name': file_name,
                'metainfo_id': info_hash,
                'peers_info': [{
                    'peer_id': peer_id,
                    'pieces': list(range(len(pieces)))
                }]
            }
            self.db.add_file(file_data)

            # Update peer piece info
            peer = self.db.get_peer(peer_id)
            if peer:
                for i, piece in enumerate(pieces):
                    peer['piece_info'].append({
                        'metainfo_id': info_hash,
                        'index': i,
                        'piece': piece
                    })
                self.db.update_peer_pieces(peer_id, peer['piece_info'])

            return True

        except Exception as e:
            log_event("ERROR", f"Error uploading file: {e}", "error")
            return False

    def get_peer_from_file(self, torrent_file: str) -> List[Dict]:
        """Get peers related to torrent file"""
        try:
            # Get info hash from torrent file
            info_hash = self._get_info_hash(torrent_file)
            if not info_hash:
                return []
                
            # Get file entry
            file_entry = self.db.get_file(info_hash)
            if not file_entry:
                return []

            # Get peer information
            peers = []
            for peer_info in file_entry['peers_info']:
                peer = self.db.get_peer(peer_info['peer_id'])
                if peer:
                    peers.append({
                        'peer_id': peer['peer_id'],
                        'ip_address': peer['ip_address'],
                        'port': peer['port'],
                        'pieces': peer_info['pieces']
                    })

            return peers

        except Exception as e:
            log_event("ERROR", f"Error getting peers for file: {e}", "error")
            return []

    def get_new_piece(self, torrent_file: str, peer_id: str) -> List[int]:
        """Get pieces needed for peer to complete file"""
        try:
            # Get info hash
            info_hash = self._get_info_hash(torrent_file)
            if not info_hash:
                return []

            # Get torrent info
            torrent = self.db.get_torrent(info_hash)
            if not torrent:
                return []

            # Get pieces peer already has
            peer = self.db.get_peer(peer_id)
            if not peer:
                return []

            existing_pieces = set()
            for piece_info in peer['piece_info']:
                if piece_info['metainfo_id'] == info_hash:
                    existing_pieces.add(piece_info['index'])

            # Return missing pieces
            total_pieces = len(torrent['info']['pieces'])
            return [i for i in range(total_pieces) if i not in existing_pieces]

        except Exception as e:
            log_event("ERROR", f"Error getting new pieces: {e}", "error")
            return []

    def run_peer_server(self, ip: str, port: int):
        """Start peer server to handle peer connections"""
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.bind((ip, port))
            self.server_socket.listen(5)
            self.is_running = True
            
            log_event("TRACKER", f"Tracker server running on {ip}:{port}", "info")
            
            # Start cleanup thread
            cleanup_thread = threading.Thread(target=self._cleanup_inactive_peers)
            cleanup_thread.daemon = True
            cleanup_thread.start()
            
            while self.is_running:
                try:
                    client_socket, addr = self.server_socket.accept()
                    thread = threading.Thread(
                        target=self._handle_peer_connection,
                        args=(client_socket, addr)
                    )
                    thread.daemon = True
                    thread.start()
                except Exception as e:
                    log_event("ERROR", f"Error accepting connection: {e}", "error")
                    
        except Exception as e:
            log_event("ERROR", f"Tracker server error: {e}", "error")
        finally:
            if self.server_socket:
                self.server_socket.close()

    def _cleanup_inactive_peers(self):
        """Remove inactive peers periodically"""
        while self.is_running:
            try:
                self.db.remove_inactive_peers(Config.PEER_TIMEOUT)
                time.sleep(Config.TRACKER_CLEANUP_INTERVAL)
            except Exception as e:
                log_event("ERROR", f"Error in cleanup: {e}", "error")

    def _get_info_hash(self, torrent_file: str) -> Optional[str]:
        """Get info hash from torrent file"""
        try:
            with open(torrent_file, 'rb') as f:
                data = bencodepy.decode(f.read())
                info = data[b'info']
                return hashlib.sha1(bencodepy.encode(info)).hexdigest()
        except Exception as e:
            log_event("ERROR", f"Error getting info hash: {e}", "error")
            return None

    def _generate_info_hash(self, file_name: str, pieces: List[bytes], 
                          file_length: int) -> str:
        """Generate info hash for new torrent"""
        info = {
            'name': file_name,
            'piece length': Config.PIECE_LENGTH,
            'pieces': b''.join(pieces),
            'length': file_length
        }
        return hashlib.sha1(bencodepy.encode(info)).hexdigest()

    def _handle_peer_connection(self, client_socket: socket.socket, addr: tuple):
        """Handle peer connection and requests"""
        try:
            # Receive peer registration
            data = client_socket.recv(1024).decode()
            peer_info = json.loads(data)
            
            peer_id = peer_info.get('peer_id')
            if not peer_id:
                raise ValueError("Missing peer_id")
                
            # Store connection
            with self._lock:
                self.connected_peers[peer_id] = {
                    'socket': client_socket,
                    'address': addr,
                    'last_seen': time.time()
                }
            
            # Handle peer requests
            while True:
                data = client_socket.recv(1024).decode()
                if not data:
                    break
                    
                request = json.loads(data)
                response = self._handle_peer_request(peer_id, request)
                
                # Send response
                client_socket.sendall(json.dumps(response).encode())
                
                # Update last seen
                with self._lock:
                    if peer_id in self.connected_peers:
                        self.connected_peers[peer_id]['last_seen'] = time.time()
                
        except Exception as e:
            log_event("ERROR", f"Error handling peer {addr}: {e}", "error")
        finally:
            # Cleanup on disconnect
            with self._lock:
                if peer_id in self.connected_peers:
                    del self.connected_peers[peer_id]
            client_socket.close()

    def _handle_peer_request(self, peer_id: str, request: Dict) -> Dict:
        """Handle different types of peer requests"""
        try:
            request_type = request.get('type')
            
            if request_type == 'get_peers':
                # Get peers for torrent
                torrent_hash = request.get('info_hash')
                peers = self.get_peer_from_file(torrent_hash)
                return {
                    'status': 'success',
                    'peers': peers
                }
                
            elif request_type == 'get_pieces':
                # Get needed pieces
                torrent_hash = request.get('info_hash') 
                pieces = self.get_new_piece(torrent_hash, peer_id)
                return {
                    'status': 'success',
                    'pieces': pieces
                }
                
            elif request_type == 'update_pieces':
                # Update peer's pieces
                torrent_hash = request.get('info_hash')
                pieces = request.get('pieces', [])
                self._update_peer_pieces(peer_id, torrent_hash, pieces)
                return {'status': 'success'}
                
            else:
                return {
                    'status': 'error',
                    'message': 'Unknown request type'
                }
                
        except Exception as e:
            return {
                'status': 'error',
                'message': str(e)
            }

    def _update_peer_pieces(self, peer_id: str, torrent_hash: str, pieces: List[int]):
        """Update peer's piece information"""
        try:
            peer = self.db.get_peer(peer_id)
            if not peer:
                return
                
            # Update piece info
            updated_pieces = []
            for piece_info in peer['piece_info']:
                if piece_info['metainfo_id'] != torrent_hash:
                    updated_pieces.append(piece_info)
                    
            for piece_index in pieces:
                updated_pieces.append({
                    'metainfo_id': torrent_hash,
                    'index': piece_index,
                    'piece': None  # Actual piece data not stored in peer info
                })
                
            self.db.update_peer_pieces(peer_id, updated_pieces)
            
            # Update file entry
            file_entry = self.db.get_file(torrent_hash)
            if file_entry:
                updated = False
                for peer_info in file_entry['peers_info']:
                    if peer_info['peer_id'] == peer_id:
                        peer_info['pieces'] = pieces
                        updated = True
                        break
                        
                if not updated:
                    file_entry['peers_info'].append({
                        'peer_id': peer_id,
                        'pieces': pieces
                    })
                    
                self.db.update_file(torrent_hash, file_entry)
                
        except Exception as e:
            log_event("ERROR", f"Error updating peer pieces: {e}", "error")

    def decode_torrent_file(self, torrent_file: str) -> str:
        """Decode torrent file and return info hash"""
        try:
            # Read torrent file and extract info hash
            with open(torrent_file, 'rb') as f:
                data = f.read()
                info_hash = hashlib.sha1(data).hexdigest()
                return info_hash
        except Exception as e:
            log_event("ERROR", f"Error decoding torrent file: {e}", "error")
            return "" 