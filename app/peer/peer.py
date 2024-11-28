import socket
import threading
import queue
from typing import List, Dict, Optional, Set
from app.database.peer_db import PeerDatabase
from app.utils.helpers import log_event
from app.config import Config
import time
from app.torrent.piece import verify_piece
from dataclasses import dataclass
from collections import defaultdict
import json
from app.torrent.torrent import TorrentHandler
from app.utils.torrent_utils import get_info_hash
import signal
import base64
import os

@dataclass
class PieceRequest:
    """Thông tin request piece từ peer khác"""
    piece_index: int
    peer_id: str
    status: str  # 'pending', 'downloading', 'completed', 'failed'
    attempts: int = 0

    def __lt__(self, other):
        """So sánh để sắp xếp trong PriorityQueue"""
        if not isinstance(other, PieceRequest):
            return NotImplemented
        # Ưu tiên piece có số lần thử ít hơn
        return self.attempts < other.attempts

    def __eq__(self, other):
        """So sánh bằng"""
        if not isinstance(other, PieceRequest):
            return NotImplemented
        return (self.piece_index == other.piece_index and 
                self.peer_id == other.peer_id and 
                self.attempts == other.attempts)

class PeerNode:
    """Peer node để upload/download pieces"""
    
    def __init__(self, ip: str, port: int, peer_id: str):
        self.ip = ip
        self.port = port
        self.peer_id = peer_id
        self.db = PeerDatabase()  # Chỉ sử dụng PeerDatabase
        self._register_peer()
        
        # Threading controls
        self._lock = threading.Lock()
        self.is_running = False
        self.download_queue = queue.PriorityQueue()  # Priority queue for piece requests
        self.active_downloads = {}  # Track active downloads
        self.completed_pieces = set()  # Successfully downloaded pieces
        self.failed_pieces = defaultdict(int)  # Track failed attempts per piece
        
        # Connection management
        self.connected_peers = {}  # Active peer connections
        self.max_connections = Config.MAX_PEER_CONNECTIONS
        self.retry_count = Config.MAX_RETRIES
        
        # Statistics
        self.download_speed = defaultdict(float)  # Speed per peer
        self.upload_speed = defaultdict(float)
        self.peer_scores = defaultdict(float)  # Score for peer selection
        self.server_socket = None  # Thêm biến để lưu server socket
        # Đăng ký signal handler
        signal.signal(signal.SIGINT, self._signal_handler)

        self.peer_assignments = {}  # Track peer -> thread assignments
        self._assignment_lock = threading.Lock()  # Lock for peer assignments
        self._connect_lock = threading.Lock()  # Lock cho việc connect to peer

        self.unavailable_pieces = set()  # Pieces không có peer nào có

    def _register_peer(self):
        """Register peer trong database"""
        try:
            # Kiểm tra peer đã tồn tại chưa
            existing_peer = self.db.get_peer(self.peer_id)
            
            if existing_peer:
                # Cập nhật thông tin mới
                self.db.update_peer_connection(
                    self.peer_id,
                    self.ip,
                    self.port
                )
                log_event("PEER", f"Updated peer {self.peer_id} {self.ip}:{self.port} connection info", "info")
            else:
                # Tạo peer mới
                peer_data = {
                    'peer_id': self.peer_id,
                    'ip_address': self.ip,
                    'port': self.port,
                    'piece_info': []  # Danh sách pieces đang giữ
                }
                if not self.db.add_peer(peer_data):
                    raise Exception(f"Failed to register peer {self.peer_id}")
                log_event("PEER", f"Registered new peer {self.peer_id} {self.ip}:{self.port}", "info")
                
        except Exception as e:
            log_event("ERROR", f"Error registering peer: {e}", "error")
        
    def start_download(self, torrent_data: Dict, peer_list: List[Dict], 
                      needed_pieces: List[int]) -> bool:

        try:
            self.is_running = True
            
            # Khởi tạo trạng thái download
            with self._lock:
                self.completed_pieces.clear()
                self.failed_pieces.clear()
                self.active_downloads.clear()
            
            log_event("PEER", f"Starting download for {torrent_data['info_hash']}", "start")

            # Queue initial piece requests trước
            log_event("PEER", "Queueing pieces for download", "info")
            self._queue_piece_requests(needed_pieces, peer_list)
            
            # Start connection manager thread
            conn_manager = threading.Thread(target=self._manage_peer_connections,
                                         args=(peer_list,))
            conn_manager.daemon = True
            conn_manager.start()
            

            log_event("PEER", "Starting download threads", "info")
            # Start download manager threads
            download_threads = []
            for i in range(len(peer_list)):
                thread = threading.Thread(
                    target=self._download_manager,
                    args=(torrent_data, peer_list),
                    name=f"DownloadThread-{i}"
                )
                thread.daemon = True
                download_threads.append(thread)
                thread.start()
            
            
            # Wait for completion or failure
            while self.is_running:
                completed_count = 0
                failed_pieces_snapshot = {}
                
                with self._lock:
                    completed_count = len(self.completed_pieces)
                    failed_pieces_snapshot = self.failed_pieces.copy()
                
                if completed_count == len(needed_pieces):
                    with self._lock:
                        # Update peer's pieces
                        self._update_completed_pieces(torrent_data['info_hash'])
                        # Update file info
                        self._update_file_info(torrent_data['info_hash'], self.completed_pieces)
                        log_event("PEER", f"Download completed for {torrent_data['info_hash']}", "success")
                    
                    self.is_running = False
                    self._close_all_connections()
                    return True
                
                if all(failed_pieces_snapshot[p] >= self.retry_count for p in needed_pieces):
                    return False
                
                # Kiểm tra pieces không có peer nào có
                if self.unavailable_pieces:
                    log_event("ERROR", f"Cannot complete download. Missing pieces: {self.unavailable_pieces}", "error")
                    return False
                
                time.sleep(0.1)
            
            # Kiểm tra lần cuối
            with self._lock:
                return len(self.completed_pieces) == len(needed_pieces)
            
        except Exception as e:
            log_event("ERROR", f"Download failed: {e}", "error")
            return False
        finally:
            self.is_running = False

    def _update_completed_pieces(self, info_hash: str):
        """Cập nhật pieces đã download vào database"""
        piece_info = []
        for piece_index in self.completed_pieces:
            piece_info.append({
                'metainfo_id': info_hash,
                'index': piece_index,
                'piece': self.active_downloads[piece_index]
            })
        self.db.update_peer_pieces(self.peer_id, piece_info)

    def _queue_piece_requests(self, needed_pieces: List[int], peer_list: List[Dict]):
        """Queue piece requests với peer selection thông minh"""
        try:
            # Group pieces theo peer để mỗi peer được xử lý bởi một thread
            pieces_by_peer = defaultdict(list)
            peer_scores = self._calculate_peer_scores(peer_list)
            
            log_event("PEER", f"Queueing {len(needed_pieces)} pieces", "info")

            # 1. Phân pieces cho các peers dựa trên score
            for piece_index in needed_pieces:
                # Tìm peers có piece này
                available_peers = [
                    peer for peer in peer_list 
                    if piece_index in peer.get('pieces', [])
                ]
                
                if not available_peers:
                    log_event("PEER", f"No peers available for piece {piece_index}", "info")
                    continue
                    
                # Sắp xếp peers theo score và chọn peer tốt nhất
                available_peers.sort(key=lambda p: peer_scores[p['peer_id']], reverse=True)
                best_peer = available_peers[0]
                
                # Thêm piece vào nhóm của peer được chọn
                pieces_by_peer[best_peer['peer_id']].append(piece_index)

            # 2. Queue các pieces theo nhóm peer
            for peer_id, pieces in pieces_by_peer.items():
                # Tính priority cho cả nhóm pieces của peer này
                priority = len(pieces)  # Peer có nhiều pieces sẽ có priority cao hơn
                
                # Queue tất cả pieces của peer này cùng một lúc
                for piece_index in pieces:
                    self.download_queue.put((
                        priority,
                        PieceRequest(
                            piece_index=piece_index,
                            peer_id=peer_id,
                            status='pending'
                        )
                    ))
                
                log_event("PEER", f"Queued {len(pieces)} pieces from peer {peer_id}", "info")
            
        except Exception as e:
            log_event("ERROR", f"Error queueing piece requests: {e}", "error")

    def _calculate_peer_scores(self, peer_list: List[Dict]) -> Dict[str, float]:
        """Tính điểm cho peer selection"""
        scores = {}
        for peer in peer_list:
            peer_id = peer['peer_id']
            score = 0.0
            
            # Xét tốc độ download
            speed = self.download_speed[peer_id]
            if speed > 0:
                score += min(speed / 1024/1024, 10.0)  # Max 10 điểm cho tốc độ
                
            # Xét tỷ lệ thành công
            success_rate = self._get_peer_success_rate(peer_id)
            score += success_rate * 5  # Max 5 điểm cho độ tin cậy
            
            # Xét độ ổn định kết nối
            if peer_id in self.connected_peers:
                score += 2  # Bonus cho peers đã kết nối
                
            scores[peer_id] = score
            
        return scores

    def _get_peer_success_rate(self, peer_id: str) -> float:
        """Tính tỷ lệ download thành công từ peer"""
        total_attempts = (self.failed_pieces[peer_id] + 
                        len([p for p in self.completed_pieces 
                             if self.active_downloads[p]['peer_id'] == peer_id]))
        if total_attempts == 0:
            return 0.5  # Default score for new peers
        return len([p for p in self.completed_pieces 
                   if self.active_downloads[p]['peer_id'] == peer_id]) / total_attempts

    def _download_piece(self, piece_index: int, peer_id: str, torrent_data: Dict):
        try:
            sock = self.connected_peers.get(peer_id)
            if not sock:
                log_event("PEER", f"No socket connection for peer {peer_id}", "error")
                return None
            
            # Gửi request
            request = {
                'type': 'request_piece',
                'piece_index': piece_index,
                'peer_id': self.peer_id,
                'info_hash': torrent_data['info_hash']
            }
            sock.sendall(json.dumps(request).encode())
            
            # Nhận response
            total_data = b''
            while True:
                chunk = sock.recv(8192)
                if not chunk:
                    break
                total_data += chunk
                # Kiểm tra marker kết thúc
                if b'###END###' in total_data:
                    break
                
            try:
                response = json.loads(total_data.decode())
                
                # Xử lý piece data và verify
                encoded_data = response.get('piece_data')
                if not encoded_data:
                    log_event("PEER", f"No piece data in response", "error")
                    return None
                
                #log_event("PEER", f"Decoded piece data: {encoded_data}", "info")
                piece_data = base64.b64decode(encoded_data)
                log_event("PEER", f"Received piece {piece_index} (size: {len(piece_data)} bytes)", "info")

                if verify_piece(piece_data, piece_index, torrent_data):
                    # Gửi ACK
                    sock.sendall(b'ACK')
                    log_event("PEER", f"Successfully verified and ACKed piece {piece_index}", "info")
                    log_event("PEER", f"Downloaded piece {piece_index} (size: {len(piece_data)} bytes) successfully from peer {peer_id}", "success")
                    return piece_data
                    
                return None
                
            except json.JSONDecodeError:
                log_event("ERROR", f"Invalid JSON response: {total_data[:100]}...", "error")
                return None
                
        except Exception as e:
            log_event("ERROR", f"Piece download failed: {e}", "error")
            return None

    def _connect_to_peer(self, peer: Dict) -> bool:
        """Thiết lập kết nối tới peer"""
        # Đảm bảo chỉ một thread có thể connect tại một thời điểm
        try:
            with self._lock:
            # Kiểm tra xem peer đã được kết nối chưa
                if peer['peer_id'] in self.connected_peers:
                    return True

            with self._connect_lock: 
                log_event("PEER", f"Connecting to peer {peer['peer_id']} at {peer['ip_address']}:{peer['port']}", "info")
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(Config.SOCKET_TIMEOUT)
                sock.connect((peer['ip_address'], peer['port']))

                handshake = {
                    'peer_id': self.peer_id,
                    'type': 'handshake'
                }
                sock.sendall(json.dumps(handshake).encode())
                response = json.loads(sock.recv(1024).decode())
                
                if response.get('status') != 'success':
                    log_event("PEER", f"Handshake failed with peer {peer['peer_id']}: {response.get('message')}", "error") 
                    return False

            # Lưu kết nối nếu handshake thành công
            with self._lock:
                self.connected_peers[peer['peer_id']] = sock

            log_event("PEER", f"Successfully connected to peer {peer['peer_id']}", "info")
            return True
            
        except Exception as e:
            log_event("ERROR", f"Peer connection failed: {e}", "error")
            return False

    def _update_download_speed(self, peer_id: str, bytes_received: int):
        """Cập nhật thống kê tốc độ download"""
        with self._lock:
            old_speed = self.download_speed[peer_id]
            new_speed = bytes_received / Config.PIECE_TIMEOUT
            self.download_speed[peer_id] = (old_speed * 0.7 + new_speed * 0.3)

    def _is_connection_alive(self, peer_id: str) -> bool:
        """Kiểm tra kết nối còn sống không"""
        with self._lock:
            try:
                sock = self.connected_peers[peer_id]
                sock.settimeout(0.1)
                # Send keepalive
                sock.sendall(b'')
                return True
            except:
                return False

    def _close_peer_connection(self, peer_id: str):
        """Đóng kết nối với peer"""
        try:
            sock = self.connected_peers[peer_id]
            sock.close()
        except:
            pass
        finally:
            with self._lock:
                if peer_id in self.connected_peers:
                    del self.connected_peers[peer_id]

    def _close_all_connections(self):
        """Đóng tất cả kết nối sau khi download xong"""
        with self._lock:
            for peer_id, sock in list(self.connected_peers.items()):
                try:
                    sock.close()
                    del self.connected_peers[peer_id]
                    log_event("PEER", f"Closed connection with peer {peer_id}", "info")
                except Exception as e:
                    log_event("ERROR", f"Error closing connection to peer {peer_id}: {e}", "error")

    def _requeue_request(self, request: PieceRequest):
        """Đưa request thất bại vào lại queue"""
        request.attempts += 1
        if request.attempts < self.retry_count:
            self.download_queue.put((1, request))  # Priority 1 for retries

    def request_peers_from_tracker(self, torrent_file: str) -> List[Dict]:
        """
        Gửi HTTP request đến tracker để lấy danh sách peers.
        
        Args:
            torrent_file: Đường dẫn file torrent
        
        Returns:
            List[Dict]: Danh sách peers có file
        """
        try:
            # Kt nối đến tracker
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(Config.SOCKET_TIMEOUT)
            sock.connect((Config.TRACKER_HOST, Config.TRACKER_PORT))
            
            # 1. Thiết lập handshake trước
            handshake = {
                'peer_id': self.peer_id,
                'type': 'handshake'
            }
            sock.sendall(json.dumps(handshake).encode())
            
            # Đợi response của handshake
            handshake_response = json.loads(sock.recv(1024).decode())
            if handshake_response.get('status') != 'success':
                log_event("ERROR", f"Handshake failed: {handshake_response.get('message')}", "error")
                return []
            log_event("PEER", f"Handshake successful with tracker", "info")
            
            # 2. Sau khi handshake thành công, bắt đầu vòng lặp request get_peers
            while True:  
                try:
                    request = {
                        'type': 'get_peers',
                        'info_hash': get_info_hash(torrent_file)
                    }
                    sock.sendall(json.dumps(request).encode())
                    log_event("PEER", f"Sent get_peers request to tracker", "info")
                    # Đợi response của get_peers
                    response = json.loads(sock.recv(1024).decode())
                    log_event("PEER", f"Received response from tracker: {response}", "info")
                    
                    if response.get('status') == 'success':
                        peers = response.get('peers', [])
                        log_event("PEER", f"Got {len(peers)} peers from tracker", "info")
                        
                        return peers
                    else:
                        log_event("ERROR", f"Get peers failed: {response.get('message')}", "error")
                        continue  # Thử lại get_peers
                    
                except Exception as e:
                    log_event("ERROR", f"Error in request cycle: {e}", "error")
                    return []
            
            return []  # Trong trường hợp vòng lặp bị break
                
        except Exception as e:
            log_event("ERROR", f"Error requesting peers from tracker: {e}", "error")
            return []
        finally:
            sock.close()

    def _manage_peer_connections(self, peer_list: List[Dict]):
        while self.is_running:
            try:
                # 1. Xóa kết nối chết
                dead_peers = []
                with self._lock:
                    for peer_id in list(self.connected_peers.keys()):
                        if not self._is_connection_alive(peer_id):
                            dead_peers.append(peer_id)
                            
                # Xóa kết nối ngoài lock
                for peer_id in dead_peers:
                    self._close_peer_connection(peer_id)
                    
                # 2. Tìm peer mới
                need_connection = False
                available_peers = []
                with self._lock:
                    if len(self.connected_peers) < self.max_connections:
                        available_peers = [
                            peer for peer in peer_list
                            if peer['peer_id'] not in self.connected_peers
                        ]
                        need_connection = True
                        
                # Kết nối ngoài lock
                if need_connection:
                    for peer in available_peers:
                        if self._connect_to_peer(peer):
                            log_event("PEER", f"Connected to peer {peer['peer_id']}", "info")
                            break
                            
                time.sleep(1)
                    
            except Exception as e:
                log_event("ERROR", f"Connection manager error: {e}", "error")

    def _download_manager(self, torrent_data: Dict, peer_list: List[Dict]):
        thread_name = threading.current_thread().name
        current_peer_id = None
        log_event("PEER", f"{thread_name} started", "start")

        try:
            while self.is_running:
                try:
                    # Lấy request từ queue
                    try:
                        priority, request = self.download_queue.get(timeout=1)
                    except queue.Empty:
                        continue

                    peer_id = request.peer_id
                    piece_index = request.piece_index

                    # Kiểm tra piece đã download chưa
                    with self._lock:
                        if piece_index in self.completed_pieces:
                            log_event("PEER", f"Piece {piece_index} already downloaded, skipping", "info")
                            self.download_queue.task_done()
                            continue

                    # Kiểm tra thread assignment
                    with self._assignment_lock:
                        if peer_id in self.peer_assignments:
                            if self.peer_assignments[peer_id] != thread_name:
                                self.download_queue.put((priority, request))
                                continue
                        elif current_peer_id is None:
                            self.peer_assignments[peer_id] = thread_name
                            current_peer_id = peer_id
                            log_event("PEER", f"{thread_name} assigned to peer {current_peer_id}", "info")
                        elif current_peer_id != peer_id:
                            self.download_queue.put((priority, request))
                            continue

                    # Thử kết nối lại nếu mất kết nối
                    reconnect_timeout = 20
                    reconnect_start = time.time()
                    connected = False

                    while time.time() - reconnect_start < reconnect_timeout:
                        if self._is_connection_alive(peer_id):
                            connected = True
                            break
                        
                        log_event("PEER", f"Attempting to reconnect to {peer_id}", "info")
                        peer_info = next((p for p in peer_list if p['peer_id'] == peer_id), None)
                        if peer_info and self._connect_to_peer(peer_info):
                            connected = True
                            break
                        
                        time.sleep(1)

                    if not connected:
                        log_event("PEER", f"Failed to reconnect to {peer_id} after {reconnect_timeout}s", "error")
                        
                        # Cleanup và reassign pieces
                        self._close_peer_connection(peer_id)
                        
                        # Cập nhật peer list và reassign pieces
                        with self._lock:
                            peer_list = [p for p in peer_list if p['peer_id'] != peer_id]
                            self._reassign_pieces(peer_id, peer_list)

                        # Reset thread state
                        with self._assignment_lock:
                            if current_peer_id in self.peer_assignments:
                                del self.peer_assignments[current_peer_id]
                            current_peer_id = None
                        
                        self.download_queue.task_done()
                        continue

                    # Download piece
                    log_event("PEER", f"Downloading piece {piece_index} from {peer_id}", "info")
                    piece_data = self._download_piece(piece_index, peer_id, torrent_data)
                    log_event("PEER", f"AFTER DOWNLOADING", "info")

                    if piece_data:
                        # Update peer score trước
                        self._update_peer_score(peer_id, True)
                        
                        # Sau đó mới update trạng thái download
                        with self._lock:
                            self.completed_pieces.add(piece_index)
                            self.active_downloads[piece_index] = piece_data
                            log_event("PEER", f"Successfully downloaded piece {piece_index}", "success")
                    else:
                        # Update peer score trước
                        self._update_peer_score(peer_id, False)
                        
                        # Sau đó mới update trạng thái failed
                        with self._lock:
                            self.failed_pieces[piece_index] += 1
                            if self.failed_pieces[piece_index] < self.retry_count:
                                self._requeue_request(request)
                            log_event("PEER", f"Failed to download piece {piece_index}", "error")

                    self.download_queue.task_done()

                except Exception as e:
                    log_event("ERROR", f"{thread_name} error: {e}", "error")
                    # Cleanup khi có lỗi
                    with self._assignment_lock:
                        if current_peer_id in self.peer_assignments:
                            del self.peer_assignments[current_peer_id]
                        current_peer_id = None
                    
        except Exception as e:
            log_event("ERROR", f"{thread_name} fatal error: {e}", "error")
        finally:
            # Cleanup khi thread kết thúc
            with self._assignment_lock:
                if current_peer_id in self.peer_assignments:
                    del self.peer_assignments[current_peer_id]
            log_event("PEER", f"{thread_name} stopped", "info")

    def _handle_peer_request(self, client_socket: socket.socket, request: Dict):
        """Xử lý các request từ peer khác"""
        try:
            request_type = request.get('type')
            
            if request_type == 'handshake':
                # Xử lý handshake...
                peer_id = request.get('peer_id')
                if peer_id:
                    self.connected_peers[peer_id] = client_socket
                    log_event("PEER", f"Handshake successful with peer {peer_id}", "info")
                    response = {
                        'status': 'success',
                        'message': 'Handshake successful'
                    }
                else:
                    response = {
                        'status': 'error',
                        'message': 'Missing peer_id'
                    }
                client_socket.sendall(json.dumps(response).encode())
                
            elif request_type == 'request_piece':
                piece_index = request.get('piece_index')
                info_hash = request.get('info_hash')
                
                log_event("PEER", f"Received piece request for index {piece_index}", "info")
                
                # Lấy nội dung thực từ DB
                piece_data = self.db.get_piece_content(info_hash, piece_index)
                if piece_data:
                    log_event("PEER", f"Found piece {piece_index} (size: {len(piece_data)} bytes)", "info")
                    
                    # Encode piece data thành base64 string
                    encoded_data = base64.b64encode(piece_data).decode('utf-8')
                    
                    # Gửi response với marker đặc biệt để phân biệt kết thúc
                    response = {
                        'status': 'success',
                        'piece_data': encoded_data,
                        'end_marker': '###END###'  # Marker để nhận biết kết thúc response
                    }
                    response_json = json.dumps(response)
                    
                    # Gửi response theo chunks
                    chunk_size = 4096
                    for i in range(0, len(response_json), chunk_size):
                        chunk = response_json[i:i + chunk_size].encode()
                        client_socket.sendall(chunk)
                    
                    # Đợi ACK với timeout
                    client_socket.settimeout(5.0)
                    try:
                        ack_data = client_socket.recv(1024)
                        if ack_data == b'ACK':
                            log_event("PEER", "Received valid ACK", "info")
                        else:
                            log_event("PEER", f"Invalid ACK data: {ack_data}", "error")
                    except socket.timeout:
                        log_event("PEER", "Timeout waiting for ACK", "error")
                    finally:
                        client_socket.settimeout(None)
                    
                else:
                    response = {
                        'status': 'error',
                        'message': 'Piece not found'
                    }
                    client_socket.sendall(json.dumps(response).encode())

      
        except Exception as e:
            log_event("ERROR", f"Error handling request: {e}", "error")

    def _handle_peer_connection(self, client_socket: socket.socket):
        """Xử lý kết nối từ peer khác."""
        try:
            while True:
                data = client_socket.recv(1024).decode()
                if not data:
                    break
                    
                request = json.loads(data)
                log_event("PEER", f"Received request from peer: {request}", "info")
                self._handle_peer_request(client_socket, request)
                
                    
        except Exception as e:
            log_event("ERROR", f"Connection handler error: {e}", "error")

    def _signal_handler(self, signum, frame):
        """Xử lý signal Ctrl+C"""
        log_event("PEER", "Received shutdown signal, stopping server...", "info")
        self.stop_server()

    def stop_server(self):
        """Dừng peer server gracefully"""
        try:
            self.is_running = False
            # Đóng server socket để dừng accept()
            if self.server_socket:
                self.server_socket.close()
            
            # Đóng tất cả kết nối peer
            with self._lock:
                for peer_id, sock in list(self.connected_peers.items()):
                    try:
                        sock.close()
                    except:
                        pass
                self.connected_peers.clear()
            
            log_event("PEER", "Server stopped", "info")
        except Exception as e:
            log_event("ERROR", f"Error stopping server: {e}", "error")

    def start_peer_server(self):
        """Khởi động server cho peer để lắng nghe các request từ peers khác."""
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.bind((self.ip, self.port))
            self.server_socket.listen(5)
            self.is_running = True
            log_event("PEER", f"Peer server running on {self.ip}:{self.port}", "info")

            while self.is_running:
                try:
                    # Set timeout để có thể check is_running
                    self.server_socket.settimeout(3.0)
                    try:
                        client_socket, addr = self.server_socket.accept()
                        log_event("PEER", f"Connection from {addr}", "info")
                        
                        # Tạo thread mới để xử lý kết nối
                        client_thread = threading.Thread(
                            target=self._handle_peer_connection,
                            args=(client_socket,)
                        )
                        client_thread.daemon = True
                        client_thread.start()
                        
                    except socket.timeout:
                        # Timeout là bình thường, tiếp tục vòng lặp
                        continue
                        
                except Exception as e:
                    if self.is_running:  # Chỉ log error nếu server vẫn đang chạy
                        log_event("ERROR", f"Error accepting connection: {e}", "error")
                        
        except Exception as e:
            log_event("ERROR", f"Error starting peer server: {e}", "error")
        finally:
            self.stop_server()

    def download_file(self, torrent_file: str, output_path: str) -> bool:
        """
        Download file từ torrent.
        
        Args:
            torrent_file: Đường dẫn file torrent
            output_path: Đường dẫn lưu file
        """
        try:
            # 1. Đọc thông tin torrent
            torrent_handler = TorrentHandler()
            torrent_data = torrent_handler.read_torrent_file(torrent_file)
            if not torrent_data:
                raise ValueError("Failed to read torrent file")
            log_event("PEER", f"Read torrent file: {torrent_data['info']['name']}", "info")
            
            # 2. Lấy danh sách peers từ tracker
            peers = self.request_peers_from_tracker(torrent_file)
            if not peers:
                raise ValueError("No peers available")
            
            log_event("PEER", f"Remove self peer {self.peer_id} from peers list", "info")
            for peer in peers:
                if peer['peer_id'] == self.peer_id:
                    peers.remove(peer)

            log_event("PEER", f"Found {len(peers)} peers with file", "info")
            log_event("PEER", f"Peers: {peers}", "info")

            # 3. Tính toán pieces cần download
            total_pieces = len(base64.b64decode(torrent_data['info']['pieces'])) // 20
            needed_pieces = list(range(total_pieces))
            log_event("PEER", f"Need to download {len(needed_pieces)} pieces (total pieces: {total_pieces})", "info")
            
            # 4. Bắt đầu download
            if not self.start_download(torrent_data, peers, needed_pieces):
                raise ValueError("Failed to download pieces")
            
            # 5. Gộp pieces thành file hoàn chỉnh
            from app.torrent.piece import combine_pieces
            if not combine_pieces(
                [self.active_downloads[i] for i in sorted(self.completed_pieces)],
                output_path
            ):
                raise ValueError("Failed to save file")
            
            log_event("PEER", f"Successfully downloaded file to {output_path}", "success")
            return True
            
        except Exception as e:
            log_event("ERROR", f"Download failed: {e}", "error")
            return False

    def _update_peer_score(self, peer_id: str, success: bool):
        """
        Cập nhật điểm số của peer dựa trên kết quả download.
        
        Args:
            peer_id: ID của peer
            success: True nếu download thành công, False nếu thất bại
        """

        current_score = self.peer_scores.get(peer_id, 0.0)
        
        if success:
            # Tăng điểm nếu thành công
            new_score = min(current_score + 1.0, 10.0)  # Max score là 10
        else:
            # Giảm điểm nếu thất bại
            new_score = max(current_score - 0.5, 0.0)   # Min score là 0
            
        self.peer_scores[peer_id] = new_score
        
        log_event("PEER", f"Updated score for peer {peer_id}: {new_score} ({'success' if success else 'failure'})", "info")

    def _update_file_info(self, info_hash: str, completed_pieces: Set[int]):
        """Update thông tin file sau khi download thành công"""
        try:
            # Update collection files
            self.db._update_one(
                'files',
                {'metainfo_id': info_hash},
                {
                    '$addToSet': {
                        'peers_info': {
                            'peer_id': self.peer_id,
                            'pieces': list(completed_pieces)
                        }
                    }
                }
            )
            log_event("PEER", f"Updated file info for {info_hash}", "info")
        except Exception as e:
            log_event("ERROR", f"Error updating file info: {e}", "error")

    def _reassign_pieces(self, dead_peer_id: str, peer_list: List[Dict]):
        """Phân bổ lại pieces của peer bị mất kết nối"""
        try:
            with self._lock:
                # Lấy tất cả pieces đang chờ download từ peer bị mất kết nối
                pending_pieces = [
                    req.piece_index for _, req in list(self.download_queue.queue)
                    if req.peer_id == dead_peer_id
                ]
                
                # Xóa các requests cũ của peer này khỏi queue
                self.download_queue.queue = [
                    (p, req) for p, req in list(self.download_queue.queue)
                    if req.peer_id != dead_peer_id
                ]
                
                # Lọc ra các peer còn sống
                active_peers = [p for p in peer_list if p['peer_id'] != dead_peer_id]
                
                # Phân bổ lại từng piece
                for piece_index in pending_pieces:
                    # Tìm peers có piece này
                    available_peers = [
                        peer for peer in active_peers
                        if piece_index in peer.get('pieces', [])
                    ]
                    
                    if available_peers:
                        # Chọn peer tốt nhất để assign
                        peer_scores = self._calculate_peer_scores(available_peers)
                        best_peer = max(available_peers, key=lambda p: peer_scores[p['peer_id']])
                        
                        # Tạo request mới với peer được chọn
                        new_request = PieceRequest(
                            piece_index=piece_index,
                            peer_id=best_peer['peer_id'],
                            status='pending'
                        )
                        self.download_queue.put((1, new_request))  # Priority 1 cho rescheduled pieces
                        log_event("PEER", f"Reassigned piece {piece_index} to peer {best_peer['peer_id']}", "info")
                    else:
                        # Không có peer nào khác có piece này
                        log_event("ERROR", f"No peers available for piece {piece_index}", "error")
                        self.unavailable_pieces.add(piece_index)
                    
                if self.unavailable_pieces:
                    log_event("PEER", f"Found {len(self.unavailable_pieces)} unavailable pieces", "warning")
                    
        except Exception as e:
            log_event("ERROR", f"Error reassigning pieces: {e}", "error")