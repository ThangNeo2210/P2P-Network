from typing import List, Dict, Optional
import socket
import threading
import json
import time
import os
import signal
import hashlib
import base64
from app.database.tracker_db import TrackerDatabase
from app.utils.helpers import log_event
from app.config import Config
from app.utils.torrent_utils import (
    get_info_hash,
    generate_info_hash
)
from app.torrent.piece import split_file
    
class Tracker:
    """Tracker server để quản lý peers và files"""
    
    def __init__(self):
        self.db = TrackerDatabase()  # Chỉ sử dụng TrackerDatabase
        self.server_socket = None
        self.is_running = False
        self._lock = threading.Lock()
        self.connected_peers = {}
        signal.signal(signal.SIGINT, self._signal_handler)

    def _signal_handler(self, sig, frame):
        """Handle Ctrl+C signal"""
        print("\nShutting down tracker server...")
        self.stop_server()
        import sys
        sys.exit(0)

    def stop_server(self):
        """Stop tracker server gracefully"""
        self.is_running = False
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass
        with self._lock:
            for peer_id, peer_data in self.connected_peers.items():
                try:
                    peer_data['socket'].close()
                except:
                    pass
            self.connected_peers.clear()

    def upload_file(self, file_path: str, peer_id: str, ip: str, port: int) -> bool:
        """Upload file hoặc folder và tạo torrent entries"""
        try:
            
            if not os.path.exists(file_path):
                raise ValueError(f"Path not found: {file_path}")

            
            peer_data = {
                'peer_id': peer_id,
                'ip_address': ip,
                'port': port,
                'piece_info': []  # Thêm piece_info rỗng cho peer mới
            }
            
            
            if not self.db.get_peer(peer_id):
                self.db._insert_one('peers', peer_data)
            else:
                self.db._update_one('peers', {'peer_id': peer_id}, {'$set': peer_data})

            files_to_process = []
            if os.path.isfile(file_path):
                files_to_process.append(file_path)
            elif os.path.isdir(file_path):
                files_to_process.extend([
                    os.path.join(file_path, f) 
                    for f in os.listdir(file_path)
                    if os.path.isfile(os.path.join(file_path, f))
                ])

            if not files_to_process:
                raise ValueError("No files to process")

            
            for file_path in files_to_process:
                
                pieces = split_file(file_path, Config.PIECE_LENGTH)
                if not pieces:
                    log_event("ERROR", f"Failed to split file {file_path}", "error")
                    continue

                file_name = os.path.basename(file_path)
                file_length = os.path.getsize(file_path)
                log_event("TRACKER", f"Processing file: {file_name} ({file_length} bytes)", "info")

                
                piece_hashes = [hashlib.sha1(p).digest() for p in pieces]
                concatenated_hashes = b''.join(piece_hashes)
                encoded_hashes = base64.b64encode(concatenated_hashes)

                
                info_hash = generate_info_hash(
                    file_name,
                    Config.PIECE_LENGTH,
                    encoded_hashes,
                    file_length
                )
                if not info_hash:
                    log_event("ERROR", f"Failed to generate info hash for {file_name}", "error")
                    continue

                
                torrent_data = {
                    'info_hash': info_hash,
                    'info': {
                        'name': file_name,
                        'piece_length': Config.PIECE_LENGTH,
                        'length': file_length,
                        'pieces': encoded_hashes.decode()
                    }
                }
                if not self.db.get_torrent(info_hash):
                    self.db._insert_one('torrents', torrent_data)
                else:
                    self.db._update_one('torrents', {'info_hash': info_hash}, {'$set': torrent_data})

                
                file_data = {
                    'file_name': file_name,
                    'metainfo_id': info_hash,
                    'peers_info': [{
                        'peer_id': peer_id,
                        'pieces': list(range(len(pieces)))
                    }]
                }
                
                if not self.db.get_file(info_hash):
                    self.db._insert_one('files', file_data)
                else:
                    self.db._update_one(
                        'files',
                        {'metainfo_id': info_hash},
                        {
                            '$addToSet': {
                                'peers_info': {
                                    'peer_id': peer_id,
                                    'pieces': list(range(len(pieces)))
                                }
                            }
                        }
                    )

                
                piece_info = [
                    {
                        'metainfo_id': info_hash,
                        'index': i,
                        'piece': pieces[i]
                    }
                    for i in range(len(pieces))
                ]

                
                self.db._update_one(
                    'peers',
                    {'peer_id': peer_id},
                    {'$push': {'piece_info': {'$each': piece_info}}}
                )

                log_event("TRACKER", f"Successfully processed file: {file_name}", "success")

            return True

        except Exception as e:
            log_event("ERROR", f"Error uploading file(s): {e}", "error")
            return False

    def get_peer_list(self, torrent_file: str) -> List[Dict]:
        """Get danh sách peers có pieces của file"""
        try:
            # Lấy info hash từ torrent file
            info_hash = get_info_hash(torrent_file)
            if not info_hash:
                return []
                
            # Lấy file entry từ database
            file_entry = self.db.get_file(info_hash)
            if not file_entry:
                return []

            # Trả về thông tin peers
            return [
                {
                    'peer_id': peer_info['peer_id'],
                    'ip': self.db.get_peer(peer_info['peer_id'])['ip_address'],
                    'port': self.db.get_peer(peer_info['peer_id'])['port'],
                    'pieces': peer_info['pieces']
                }
                for peer_info in file_entry['peers_info']
            ]

        except Exception as e:
            log_event("ERROR", f"Error getting peers for file: {e}", "error")
            return []

    def run_peer_server(self, ip: str, port: int):
        """Chạy tracker server để xử lý requests từ peers"""
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.settimeout(1.0)
            self.server_socket.bind((ip, port))
            self.server_socket.listen(5)
            self.is_running = True
            
            log_event("TRACKER", f"Tracker server running on {ip}:{port}", "info")
            
            # # Start cleanup thread
            # cleanup_thread = threading.Thread(target=self._cleanup_inactive_peers)
            # cleanup_thread.daemon = True  # Đảm bảo thread sẽ dừng khi chương trình chính dừng
            # cleanup_thread.start()
            
            while self.is_running:
                try:
                    client_socket, addr = self.server_socket.accept()
                    thread = threading.Thread(
                        target=self._handle_peer_connection,
                        args=(client_socket, addr)
                    )
                    thread.daemon = True
                    thread.start()
                except socket.timeout:
                    continue
                except Exception as e:
                    if self.is_running:
                        log_event("ERROR", f"Error accepting connection: {e}", "error")
                    
        except Exception as e:
            log_event("ERROR", f"Tracker server error: {e}", "error")
        finally:
            self.stop_server()

    def _handle_peer_connection(self, client_socket: socket.socket, addr: tuple):
        """Xử lý kết nối và requests từ peer"""
        peer_id = None
        try:
            # Set timeout cho socket
            client_socket.settimeout(30.0)  # Tăng timeout lên 30s
            
            while True:  # Vòng lặp để xử lý nhiều requests
                # Nhận request
                data = client_socket.recv(1024).decode()
                if not data:
                    log_event("TRACKER", f"Connection closed by peer {addr}", "info")
                    break
                
                request = json.loads(data)
                peer_id = request.get('peer_id')
                
                # Xử lý request
                response = self._handle_peer_request(peer_id, request)
                # log_event("TRACKER", f"Processing {request.get('type')} request from peer {peer_id}", "info")
                # log_event("TRACKER", f"Response: {response}", "info")
                # Gửi response
                client_socket.sendall(json.dumps(response).encode())
                log_event("TRACKER", f"Sent response to peer {peer_id}", "info")
                
                # Nếu là request get_peers, đợi thêm để đảm bảo response được gửi
                if request.get('type') == 'get_peers':
                    time.sleep(0.1)

        except Exception as e:
            log_event("ERROR", f"Error handling peer {addr}: {e}", "error")
        finally:
            try:
                client_socket.close()
                log_event("TRACKER", f"Closed connection with peer {addr}", "info")
            except Exception as e:
                log_event("ERROR", f"Error closing socket for peer {addr}: {e}", "error")

    def _handle_peer_request(self, peer_id: str, request: Dict) -> Dict:
        """Xử lý các loại request từ peer"""
        try:
            request_type = request.get('type')
            
            if request_type == 'handshake':
                # Verify peer exists in database
                peer = self.db.get_peer(peer_id)
                if not peer:
                    return {
                        'status': 'error',
                        'message': 'Peer not registered'
                    }
                
                log_event("TRACKER", f"Handshake successful with peer {peer_id}", "info")
                return {
                    'status': 'success',
                    'message': 'Handshake successful'
                }
                
            elif request_type == 'get_peers':
                info_hash = request.get('info_hash')
                if not info_hash:
                    return {'status': 'error', 'message': 'Missing info_hash'}
                 
                log_event("TRACKER", f"Get peers request for {info_hash} from {peer_id}", "info")
                file_entry = self.db.get_file(info_hash)
                if not file_entry:
                    return {'status': 'error', 'message': 'File not found'}
                
                # Return peer list excluding requesting peer
                peers = []
                for peer_info in file_entry['peers_info']:
                    if peer_info['peer_id'] != peer_id:  # Don't include requesting peer
                        peer = self.db.get_peer(peer_info['peer_id'])
                        if peer:
                            peers.append({
                                'peer_id': peer['peer_id'],
                                'ip_address': peer['ip_address'], 
                                'port': peer['port'],
                                'pieces': peer_info['pieces']
                            })
                
                return {
                    'status': 'success',
                    'peers': peers
                }
                
            elif request_type == 'update_pieces':
                # Cập nhật pieces của peer
                info_hash = request.get('info_hash')
                pieces = request.get('pieces', [])
                
                self.db.update_file_peers(info_hash, peer_id, pieces)
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