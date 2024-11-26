import bencodepy
import hashlib
import os
from typing import Dict, Optional, Tuple, List
from app.utils.helpers import log_event
from app.database.db import Database

class TorrentHandler:
    def __init__(self):
        self.db = Database()

    def decode_torrent_file(self, torrent_file: str) -> Optional[str]:
        """Decode torrent file and extract info hash"""
        try:
            with open(torrent_file, 'rb') as f:
                torrent_data = bencodepy.decode(f.read())
                info = torrent_data[b'info']
                return hashlib.sha1(bencodepy.encode(info)).hexdigest()
                
        except Exception as e:
            log_event("ERROR", f"Error decoding torrent file: {e}", "error")
            return None

    def get_torrent(self, torrent_file: str) -> Optional[Dict]:
        """Get torrent file information"""
        try:
            with open(torrent_file, 'rb') as f:
                torrent_data = bencodepy.decode(f.read())
                
            info = torrent_data[b'info']
            info_hash = hashlib.sha1(bencodepy.encode(info)).hexdigest()

            # Check if torrent exists in database
            existing_torrent = self.db.get_torrent(info_hash)
            if existing_torrent:
                return existing_torrent

            # Create new torrent entry
            torrent_data = {
                'info_hash': info_hash,
                'info': {
                    'name': info[b'name'].decode(),
                    'piece_length': info[b'piece length'],
                    'length': info[b'length'],
                    'pieces': info[b'pieces']
                }
            }
            
            self.db.add_torrent(torrent_data)
            return torrent_data

        except Exception as e:
            log_event("ERROR", f"Error getting torrent info: {e}", "error")
            return None


    def get_available_pieces(self, peer_id: str, torrent: Dict) -> List[int]:
        """Get list of pieces owned by peer"""
        try:
            peer = self.db.get_peer(peer_id)
            if not peer:
                return []
                
            available_pieces = []
            for piece_info in peer['piece_info']:
                if piece_info['metainfo_id'] == torrent['info_hash']:
                    available_pieces.append(piece_info['index'])
                    
            return available_pieces
            
        except Exception as e:
            log_event("ERROR", f"Error getting available pieces: {e}", "error")
            return []


    def get_peer_list(self, torrent: Dict) -> List[Dict]:
        """Get list of peers having pieces of torrent"""
        try:
            file_entry = self.db.get_file(torrent['info_hash'])
            if not file_entry:
                return []
                
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
            log_event("ERROR", f"Error getting peer list: {e}", "error")
            return [] 
        
    def combine_pieces(self, pieces: List[bytes], output_file: str) -> bool:
        """Combine downloaded pieces into complete file"""
        try:
            if not pieces:  
                raise ValueError("No pieces to combine")
                
            output_dir = os.path.dirname(output_file)
            if output_dir and not os.path.exists(output_dir):
                os.makedirs(output_dir)
            
            with open(output_file, 'wb') as f:
                for piece in pieces:
                    if not piece:
                        raise ValueError("Invalid piece data")
                    f.write(piece)
                
            return True
        
        except Exception as e:
            log_event("ERROR", f"Error combining pieces: {e}", "error")
            return False
    
    def verify_file(self, file_path: str, torrent: Dict) -> bool:
        """Verify downloaded file matches torrent info"""
        try:
            file_size = os.path.getsize(file_path)
            if file_size != torrent['info']['length']:
                return False
                
            # Verify pieces
            piece_length = torrent['info']['piece_length']
            with open(file_path, 'rb') as f:
                for i in range(0, file_size, piece_length):
                    piece_data = f.read(piece_length)
                    piece_hash = hashlib.sha1(piece_data).digest()
                    if piece_hash != torrent['info']['pieces'][i:i+20]:
                        return False
                        
            return True
            
        except Exception as e:
            log_event("ERROR", f"Error verifying file: {e}", "error")
            return False