import hashlib
import bencodepy
import base64
from typing import List, Optional, Dict
from app.utils.helpers import log_event

def convert_pieces_for_storage(pieces: List[bytes]) -> str:
    """Convert pieces thành base64 string để lưu vào DB"""
    try:
        # Nối các piece hashes thành một bytes object
        concatenated = b''.join(pieces)
        # Encode thành base64 string
        return base64.b64encode(concatenated).decode()
    except Exception as e:
        log_event("ERROR", f"Error converting pieces for storage: {e}", "error")
        return ""

def convert_pieces_from_storage(pieces_base64: str) -> List[bytes]:
    """Convert base64 string từ DB thành list of piece hashes"""
    try:
        # Decode base64 string thành bytes
        concatenated = base64.b64decode(pieces_base64)
        # Tách thành list of 20-byte pieces (SHA1 hashes)
        return [concatenated[i:i+20] for i in range(0, len(concatenated), 20)]
    except Exception as e:
        log_event("ERROR", f"Error converting pieces from storage: {e}", "error")
        return []

def get_info_hash(torrent_file: str) -> Optional[str]:
    """
    Get info hash from torrent file.
    """
    try:
        with open(torrent_file, 'rb') as f:
            # Đọc file thành bytes trước khi decode
            torrent_bytes = f.read()
            if not torrent_bytes:
                raise ValueError("Empty torrent file")
                
            # Decode torrent data
            data = bencodepy.decode(torrent_bytes)
            if not data or b'info' not in data:
                raise ValueError("Invalid torrent file structure")
                
            info = data[b'info']
            return hashlib.sha1(bencodepy.encode(info)).hexdigest()
            
    except Exception as e:
        log_event("ERROR", f"Error getting info hash: {e}", "error")
        return None

def generate_info_hash(file_name: str, piece_length: int, pieces: bytes, file_length: int) -> Optional[str]:
    """
    Generate info hash từ metadata.
    
    Args:
        file_name: Tên file
        piece_length: Kích thước mỗi piece
        pieces: Pieces data đã được encode base64
        file_length: Kích thước file
    """
    try:
        # Tạo info dict với pieces đã encode
        info = {
            b'name': file_name.encode(),
            b'piece length': piece_length,
            b'pieces': pieces,  # Pieces đã được encode
            b'length': file_length
        }
        
        # Tính SHA1 hash của info được encode
        return hashlib.sha1(bencodepy.encode(info)).hexdigest()
        
    except Exception as e:
        log_event("ERROR", f"Error generating info hash: {e}", "error")
        return None

def validate_torrent_info(info: Dict) -> bool:
    """
    Validate torrent info dictionary.
    
    Args:
        info: Torrent info dictionary
        
    Returns:
        bool: True if valid, False otherwise
    """
    # Các trường bắt buộc trong info dict của torrent file
    required_fields = [b'name', b'piece length', b'length', b'pieces']
    return all(field in info for field in required_fields) 