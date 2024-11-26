import os
import hashlib
from typing import List, Dict
import math
from app.utils.helpers import log_event
from app.config import Config
import time
import bencodepy

def generate_pieces(file_path: str, piece_length: int) -> List[bytes]:
    """Generate pieces from input file"""
    try:
        pieces = []
        with open(file_path, 'rb') as f:
            while True:
                piece_data = f.read(piece_length)
                if not piece_data:
                    break
                # Generate SHA1 hash for piece
                piece_hash = hashlib.sha1(piece_data).digest()
                pieces.append(piece_hash)
        return pieces
        
    except Exception as e:
        log_event("ERROR", f"Error generating pieces: {e}", "error")
        return []

def generate_info_hash(file_name: str, piece_length: int, 
                      pieces: List[bytes], file_length: int) -> str:
    """Generate info hash for torrent file"""
    try:
        # Create info dictionary
        info = {
            'name': file_name,
            'piece length': piece_length,
            'pieces': b''.join(pieces),
            'length': file_length
        }
        
        # Generate SHA1 hash of bencoded info
        import bencodepy
        info_hash = hashlib.sha1(bencodepy.encode(info)).hexdigest()
        return info_hash
        
    except Exception as e:
        log_event("ERROR", f"Error generating info hash: {e}", "error")
        return None

def create_torrent_file(file_name: str, piece_length: int,
                       pieces: List[bytes], file_length: int, 
                       output_file: str) -> bool:
    """Create torrent file from file information"""
    try:
        # Generate info hash
        info_hash = generate_info_hash(
            file_name, piece_length, pieces, file_length
        )
        if not info_hash:
            return False
            
        # Create torrent dictionary
        torrent_dict = {
            'info': {
                'name': file_name,
                'piece length': piece_length,
                'pieces': b''.join(pieces),
                'length': file_length
            },
            'info_hash': info_hash,
            'created by': 'BitTorrent Client',
            'creation date': int(time.time())
        }
        
        # Write to file
        with open(output_file, 'wb') as f:
            f.write(bencodepy.encode(torrent_dict))
            
        return True
        
    except Exception as e:
        log_event("ERROR", f"Error creating torrent file: {e}", "error")
        return False

# def combine_pieces(pieces: List[bytes], output_file: str) -> bool:
#     """Combine downloaded pieces into complete file"""
#     try:
#         if not pieces:
#             raise ValueError("No pieces to combine")
            
#         output_dir = os.path.dirname(output_file)
#         if output_dir and not os.path.exists(output_dir):
#             os.makedirs(output_dir)
            
#         with open(output_file, 'wb') as f:
#             for piece in pieces:
#                 if not piece:
#                     raise ValueError("Invalid piece data")
#                 f.write(piece)
                
#         return True
        
#     except Exception as e:
#         log_event("ERROR", f"Error combining pieces: {e}", "error")
#         return False