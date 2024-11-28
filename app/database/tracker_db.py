from typing import Dict, List, Optional
from app.database.base_db import BaseDatabase
import base64
from app.utils.torrent_utils import convert_pieces_from_storage
from app.utils.helpers import log_event
class TrackerDatabase(BaseDatabase):
    """Database interface for tracker - chỉ truy cập torrents và files"""

    def add_torrent(self, torrent_data: Dict) -> bool:
        """Thêm torrent mới"""
        try:
            # pieces đã được convert sang base64 string từ trước
            return self._insert_one('torrents', torrent_data)
        except Exception as e:
            log_event("ERROR", f"Error adding torrent: {e}", "error")
            return False

    def get_torrent(self, info_hash: str) -> Optional[Dict]:
        """Lấy thông tin torrent"""
        try:
            torrent = self._find_one('torrents', {'info_hash': info_hash})
            if torrent:
                # Convert base64 string back to list of piece hashes
                pieces_base64 = torrent['info']['pieces']
                torrent['info']['pieces'] = convert_pieces_from_storage(pieces_base64)
            return torrent
        except Exception as e:
            log_event("ERROR", f"Error getting torrent: {e}", "error")
            return None

    def add_file(self, file_data: Dict) -> bool:
        """Thêm file mới"""
        return self._insert_one('files', file_data)

    def get_file(self, info_hash: str):
        try:
            file = self._find_one('files', {'metainfo_id': info_hash})
            log_event("TRACKER", f"Found file with info_hash {info_hash}: {file is not None}", "info")
            return file
        except Exception as e:
            log_event("ERROR", f"Error getting file: {e}", "error")
            return None

    def update_file_peers(self, metainfo_id: str, peer_id: str, pieces: List[int]):
        """Cập nhật pieces của peer cho file"""
        return self._update_one(
            'files',
            {'metainfo_id': metainfo_id},
            {
                '$push': {
                    'peers_info': {
                        'peer_id': peer_id,
                        'pieces': pieces
                    }
                }
            }
        ) 
    
    def get_peer_info(self, peer_id: str) -> Optional[Dict]:
        """Lấy thông tin ip và port của peer."""
        try:
            return self._find_one('peers', {'peer_id': peer_id}, {'ip_address': 1, 'port': 1})
        except Exception as e:
            log_event("ERROR", f"Error getting peer info: {e}", "error")
            return None
    def get_peer(self, peer_id: str) -> Optional[Dict]:
        """Lấy thông tin peer từ database."""
        try:
            return self._find_one('peers', {'peer_id': peer_id})
        except Exception as e:
            log_event("ERROR", f"Error getting peer: {e}", "error")
            return None