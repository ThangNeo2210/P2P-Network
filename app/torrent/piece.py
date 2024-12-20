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
       
        pieces_base64 = torrent_data['info']['pieces']  # base64 string
        all_pieces = base64.b64decode(pieces_base64)    # bytes của concatenated hashes
        
        
        piece_hash = all_pieces[piece_index * 20:(piece_index + 1) * 20]
        

        actual_hash = hashlib.sha1(piece_data).digest()
        
        return piece_hash == actual_hash
        
    except Exception as e:
        log_event("ERROR", f"Error verifying piece: {e}", "error")
        return False

def combine_pieces(pieces: List[bytes], output_file: str) -> bool:

    try:
        if not pieces:
            raise ValueError("No pieces to combine")
            
        
        output_dir = os.path.dirname(output_file)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)
            
       
        temp_file = output_file + '.tmp'
        with open(temp_file, 'wb') as f:
            for piece in pieces:
                if not piece:
                    raise ValueError("Invalid piece data")
                f.write(piece)
                
        
        os.rename(temp_file, output_file)
        return True
        
    except Exception as e:
        log_event("ERROR", f"Error combining pieces: {e}", "error")
        if os.path.exists(temp_file):
            os.remove(temp_file)
        return False

def split_file(file_path: str, piece_length: int) -> List[bytes]:

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

