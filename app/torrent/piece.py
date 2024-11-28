import os
import hashlib
from typing import List, Dict, Optional
from app.utils.helpers import log_event
from app.config import Config
import base64
def generate_pieces(file_path: str, piece_length: int) -> List[bytes]:
    """Generate pieces hash"""
    pieces = []
    with open(file_path, 'rb') as f:
        while True:
            piece_data = f.read(piece_length)
            if not piece_data:
                break
            piece_hash = hashlib.sha1(piece_data).digest()
            pieces.append(piece_hash)  # Hash của piece
    return pieces

def verify_piece(piece_data: bytes, piece_index: int, torrent_data: Dict):
    try:
        # log_event("PEER", f"Piece length in torrent: {torrent_data['info']['piece_length']}", "info")
        # log_event("PEER", f"Actual piece data length: {len(piece_data)}", "info")
        # log_event("PEER", f"First 20 bytes of piece data: {piece_data[:20].hex()}", "info")
        
        # 1. Lấy base64 string từ torrent data và decode về bytes
        pieces_base64 = torrent_data['info']['pieces']  # base64 string
        all_pieces = base64.b64decode(pieces_base64)    # bytes của concatenated hashes
        
        # 2. Lấy hash của piece cần verify
        piece_hash = all_pieces[piece_index * 20:(piece_index + 1) * 20]
        # log_event("PEER", f"Got hash for piece {piece_index}: {piece_hash.hex()}", "info")
        
        # 3. Tính hash của piece data nhận được
        actual_hash = hashlib.sha1(piece_data).digest()
        # log_event("PEER", f"Calculated hash for piece {piece_index}: {actual_hash.hex()}", "info")
        
        return piece_hash == actual_hash
        
    except Exception as e:
        log_event("ERROR", f"Error verifying piece: {e}", "error")
        return False

def combine_pieces(pieces: List[bytes], output_file: str) -> bool:

    try:
        if not pieces:
            raise ValueError("No pieces to combine")
            
        # Tạo thư mục output nếu chưa tồn tại
        output_dir = os.path.dirname(output_file)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)
            
        # Ghi pieces vào file tạm
        temp_file = output_file + '.tmp'
        with open(temp_file, 'wb') as f:
            for piece in pieces:
                if not piece:
                    raise ValueError("Invalid piece data")
                f.write(piece)
                
        # Đổi tên file tạm thành file chính
        os.rename(temp_file, output_file)
        return True
        
    except Exception as e:
        log_event("ERROR", f"Error combining pieces: {e}", "error")
        if os.path.exists(temp_file):
            os.remove(temp_file)
        return False

def split_file(file_path: str, piece_length: int) -> List[bytes]:
    """
    Chia file thành các pieces có kích thước cố định.
    
    Args:
        file_path: Đường dẫn đến file cần chia
        piece_length: Kích thước mỗi piece
        
    Returns:
        List[bytes]: Danh sách các pieces
    """
    try:
        if not os.path.exists(file_path):
            raise ValueError(f"File not found: {file_path}")
            
        if not Config.validate_piece_length(piece_length):
            raise ValueError(f"Invalid piece length: {piece_length}")
            
        pieces = []
        with open(file_path, 'rb') as f:
            while True:
                piece_data = f.read(piece_length)
                if not piece_data:
                    break
                pieces.append(piece_data)
                
        return pieces
        
    except Exception as e:
        log_event("ERROR", f"Error splitting file: {e}", "error")
        return []

