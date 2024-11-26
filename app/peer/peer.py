import socket
import threading
import queue
from typing import List, Dict, Optional
from app.database.db import Database
from app.utils.helpers import log_event
from app.config import Config
import hashlib
import time

class PeerNode:
    def __init__(self, ip: str, port: int, peer_id: str):
        self.ip = ip
        self.port = port
        self.peer_id = peer_id
        self.piece_queue = queue.Queue()
        self._lock = threading.Lock()
        self.db = Database()
        self._register_peer()
        self.retry_count = Config.MAX_RETRIES

    def _register_peer(self):
        """Register peer in database if not exists"""
        if not self.db.get_peer(self.peer_id):
            peer_data = {
                'peer_id': self.peer_id,
                'ip_address': self.ip,
                'port': self.port,
                'piece_info': [],
                'total_uploaded': 0,
                'total_downloaded': 0,
                'failed_uploads': 0,
                'successful_uploads': 0,
                'network_stats': {
                    'upload_bandwidth': 0.0,
                    'download_bandwidth': 0.0,
                    'latency': 0.0,
                    'active_connections': 0,
                    'cpu_usage': 0.0,
                    'success_rate': 1.0,
                    'uptime': 0.0,
                    'last_update': None
                }
            }
            self.db.add_peer(peer_data)

    def get_my_peer_info(self) -> Dict:
        """Get current peer information"""
        peer = self.db.get_peer(self.peer_id)
        if not peer:
            return {
                'peer_id': self.peer_id,
                'ip_address': self.ip,
                'port': self.port
            }
        return peer

    def connect_to_peer(self, peer_ip: str, peer_port: int) -> Optional[socket.socket]:
        """Connect to another peer with retry mechanism"""
        retries = 0
        while retries < self.retry_count:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(Config.SOCKET_TIMEOUT)
                sock.connect((peer_ip, peer_port))
                return sock
            except Exception as e:
                retries += 1
                log_event("ERROR", f"Connection attempt {retries} failed: {e}", "error")
                if retries < self.retry_count:
                    time.sleep(1)  # Wait before retry
        return None

    def request_pieces_from_peers(self, peer_list: List[Dict], piece_indexes: List[int], 
                                torrent_data: Dict, available_pieces: List[int]):
        """Request pieces from multiple peers using multi-threading"""
        if not peer_list or not piece_indexes:
            log_event("ERROR", "Invalid peer list or piece indexes", "error")
            return []

        threads = []
        queue_lock = threading.Lock()
        requested_pieces = set()
        pieces = [None] * len(piece_indexes)
        active_threads = threading.Event()
        active_threads.set()

        def request_piece(peer_id: str, piece_index: int, pieces: List[bytes], 
                         requested: set, lock: threading.Lock, metainfo_id: str):
            """Request single piece with verification"""
            retries = 0
            while retries < self.retry_count and active_threads.is_set():
                try:
                    # Validate peer
                    peer = self.db.get_peer(peer_id)
                    if not peer:
                        raise ValueError(f"Peer {peer_id} not found")

                    # Connect to peer
                    sock = self.connect_to_peer(peer['ip_address'], peer['port'])
                    if not sock:
                        raise ConnectionError(f"Failed to connect to peer {peer_id}")

                    try:
                        # Send request
                        request = {
                            'type': 'request_piece',
                            'piece_index': piece_index,
                            'peer_id': self.peer_id,
                            'metainfo_id': metainfo_id
                        }
                        sock.sendall(str(request).encode())

                        # Receive with timeout
                        sock.settimeout(Config.PIECE_TIMEOUT)
                        data = sock.recv(torrent_data['piece_length'])

                        # Verify piece
                        if data and self._verify_piece(data, piece_index, torrent_data):
                            with lock:
                                pieces[piece_index] = data
                                requested.add(piece_index)
                                self._update_stats(peer_id, len(data), True)
                            return
                        else:
                            raise ValueError("Invalid piece data received")

                    finally:
                        sock.close()

                except Exception as e:
                    retries += 1
                    log_event("ERROR", f"Piece request attempt {retries} failed: {e}", "error")
                    self._update_stats(peer_id, 0, False)
                    if retries < self.retry_count:
                        time.sleep(1)  # Wait before retry

        try:
            # Create threads for each piece request
            for piece_index in piece_indexes:
                if piece_index in available_pieces:
                    continue

                # Find peer with this piece
                for peer in peer_list:
                    if piece_index in peer['pieces']:
                        thread = threading.Thread(
                            target=request_piece,
                            args=(peer['peer_id'], piece_index, pieces, requested_pieces, 
                                  queue_lock, torrent_data['info_hash'])
                        )
                        thread.daemon = True
                        threads.append(thread)
                        thread.start()
                        break

            # Wait for all threads with timeout
            for thread in threads:
                thread.join(timeout=Config.PIECE_TIMEOUT)

            # Check for incomplete pieces
            missing_pieces = [i for i, p in enumerate(pieces) if p is None]
            if missing_pieces:
                log_event("WARNING", f"Missing pieces: {missing_pieces}", "warning")

            return [p for p in pieces if p is not None]

        except Exception as e:
            log_event("ERROR", f"Error in piece request: {e}", "error")
            active_threads.clear()  # Signal threads to stop
            return []
        finally:
            active_threads.clear()

    def _verify_piece(self, piece_data: bytes, piece_index: int, torrent_data: Dict) -> bool:
        """Verify piece integrity"""
        try:
            piece_hash = hashlib.sha1(piece_data).digest()
            expected_hash = torrent_data['info']['pieces'][piece_index*20:(piece_index+1)*20]
            return piece_hash == expected_hash
        except Exception as e:
            log_event("ERROR", f"Piece verification failed: {e}", "error")
            return False

    def _update_stats(self, peer_id: str, bytes_transferred: int, success: bool):
        """Update peer statistics"""
        try:
            peer = self.db.get_peer(peer_id)
            if peer:
                if success:
                    peer['successful_uploads'] += 1
                    peer['total_downloaded'] += bytes_transferred
                else:
                    peer['failed_uploads'] += 1
                
                total_attempts = peer['successful_uploads'] + peer['failed_uploads']
                peer['network_stats']['success_rate'] = (
                    peer['successful_uploads'] / total_attempts if total_attempts > 0 else 1.0
                )
                
                if bytes_transferred > 0:
                    peer['network_stats']['download_bandwidth'] = bytes_transferred / Config.PIECE_TIMEOUT
                
                self.db.update_peer_stats(peer_id, peer['network_stats'])
        except Exception as e:
            log_event("ERROR", f"Error updating stats: {e}", "error")