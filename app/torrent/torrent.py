import bencodepy
import hashlib
import os
from typing import Dict, Optional, List
from app.utils.helpers import log_event
from app.utils.torrent_utils import (
    get_info_hash,
    generate_info_hash,
    validate_torrent_info
)
import time
from app.config import Config
import base64

class TorrentHandler:
    """Handler for torrent file operations"""
    
    def create_torrent_file(self, file_path: str, output_file: str) -> Optional[str]:

        try:
            if not os.path.exists(file_path):
                raise ValueError(f"File not found: {file_path}")

            # Generate pieces hash
            from app.torrent.piece import generate_pieces
            pieces = generate_pieces(file_path, Config.PIECE_LENGTH)
            concatenated_pieces = b''.join(pieces)  # Bytes của các SHA1 hashes
            
            # Encode pieces thành base64 để lưu vào file
            encoded_pieces = base64.b64encode(concatenated_pieces)
            
            file_name = os.path.basename(file_path)
            file_length = os.path.getsize(file_path)

            # Tạo info dict với pieces đã encode
            info_dict = {
                b'name': file_name.encode(),
                b'piece length': Config.PIECE_LENGTH,
                b'pieces': encoded_pieces,  # Dùng pieces đã encode
                b'length': file_length
            }

            # Generate info hash từ info dict với pieces đã encode
            info_hash = generate_info_hash(
                file_name,
                Config.PIECE_LENGTH,
                encoded_pieces,  # Dùng pieces đã encode để tính info_hash
                file_length
            )
            if not info_hash:
                return None

            # Create torrent dictionary
            torrent_dict = {
                b'info': info_dict,
                b'created by': b'BitTorrent Client',
                b'creation date': int(time.time()),
                b'info_hash': info_hash.encode()
            }

            # Create output directory if needed
            output_dir = os.path.dirname(output_file)
            if output_dir and not os.path.exists(output_dir):
                os.makedirs(output_dir)

            # Write torrent file
            with open(output_file, 'wb') as f:
                f.write(bencodepy.encode(torrent_dict))

            return info_hash

        except Exception as e:
            log_event("ERROR", f"Error creating torrent file: {e}", "error")
            return None

    def read_torrent_file(self, torrent_file: str) -> Optional[Dict]:
 
        try:
            if not os.path.exists(torrent_file):
                raise ValueError(f"Torrent file not found: {torrent_file}")

            with open(torrent_file, 'rb') as f:
                torrent_data = bencodepy.decode(f.read())

            info = torrent_data.get(b'info', {})
            if not validate_torrent_info(info):
                raise ValueError("Invalid torrent file structure")

            # Convert to more friendly format
            return {
                'info_hash': get_info_hash(torrent_file),
                'info': {
                    'name': info[b'name'].decode(),
                    'piece_length': info[b'piece length'],
                    'length': info[b'length'],
                    'pieces': info[b'pieces'].decode()  # Đã là base64 string từ khi tạo torrent
                },
                'created_by': torrent_data.get(b'created by', b'').decode(),
                'creation_date': torrent_data.get(b'creation date', 0)
            }

        except Exception as e:
            log_event("ERROR", f"Error reading torrent file: {e}", "error")
            return None

    def verify_torrent_file(self, torrent_file: str, original_file: str) -> bool:

        try:
            if not os.path.exists(torrent_file) or not os.path.exists(original_file):
                return False

            # Read torrent info
            torrent_info = self.read_torrent_file(torrent_file)
            if not torrent_info:
                return False

            # Verify file size
            if os.path.getsize(original_file) != torrent_info['info']['length']:
                return False

            # Verify pieces
            from app.torrent.piece import generate_pieces
            original_pieces = generate_pieces(
                original_file, 
                torrent_info['info']['piece_length']
            )
            torrent_pieces = base64.b64decode(torrent_info['info']['pieces'])
            torrent_pieces = [
                torrent_pieces[i:i+20] 
                for i in range(0, len(torrent_pieces), 20)
            ]

            return original_pieces == torrent_pieces

        except Exception as e:
            log_event("ERROR", f"Error verifying torrent file: {e}", "error")
            return False

    def get_torrent_info(self, torrent_file: str) -> Optional[Dict]:

        try:
            torrent_data = self.read_torrent_file(torrent_file)
            if not torrent_data:
                return None

            return {
                'name': torrent_data['info']['name'],
                'size': torrent_data['info']['length'],
                'piece_length': torrent_data['info']['piece_length'],
                'total_pieces': len(base64.b64decode(torrent_data['info']['pieces'])) // 20,
                'info_hash': torrent_data['info_hash'],
                'created_by': torrent_data['created_by'],
                'creation_date': torrent_data['creation_date']
            }

        except Exception as e:
            log_event("ERROR", f"Error getting torrent info: {e}", "error")
            return None