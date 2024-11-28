from typing import Dict, List, Any
from dataclasses import dataclass

@dataclass
class TorrentModel:
    """Collection torrents - Chỉ tracker có quyền truy cập"""
    name: str                # Tên file
    piece_length: int        # Độ dài tối đa của mỗi piece
    length: int             # Độ dài file
    pieces: str             # Chuỗi pieces đã mã hóa base64
    info_hash: str          # Hash của torrent để định danh

@dataclass
class FileModel:
    """Collection files - Chỉ tracker có quyền truy cập"""
    file_name: str          # Tên file
    metainfo_id: str        # ObjectId của torrent tương ứng
    peers_info: List[Dict[str, Any]]  # Danh sách peer và pieces họ đang giữ
    # peers_info structure:
    # [{
    #    'peer_id': str,
    #    'pieces': List[int]  # Danh sách index của pieces
    # }]

@dataclass
class PeerModel:
    """Collection peers - Chỉ peers có quyền truy cập"""
    peer_id: str           # ID của peer
    ip_address: str        # IP address
    port: int             # Port number
    piece_info: List[Dict[str, Any]]  # Thông tin về pieces peer đang giữ
    # piece_info structure:
    # [{
    #    'metainfo_id': str,  # ObjectId của torrent
    #    'index': int,        # Index của piece trong chuỗi pieces
    #    'piece': bytes       # Nội dung của piece
    # }] 

class FileEntry:
    def __init__(self, file_name: str, metainfo_id: str):
        self.file_name = file_name
        self.metainfo_id = metainfo_id  # info_hash
        self.pieces = []  # List of piece contents
        self.piece_hashes = []  # List of piece hashes