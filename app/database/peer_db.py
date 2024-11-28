from typing import Dict, List, Optional
from app.database.base_db import BaseDatabase
from app.utils.helpers import log_event
class PeerDatabase(BaseDatabase):
    """Database interface for peer - chỉ truy cập collection peers"""

    def add_peer(self, peer_data: Dict) -> bool:
        """Thêm peer mới"""
        return self._insert_one('peers', peer_data)

    def get_peer(self, peer_id: str) -> Optional[Dict]:
        """Lấy thông tin peer"""
        return self._find_one('peers', {'peer_id': peer_id})

    def update_peer_pieces(self, peer_id: str, piece_info: List[Dict]):
        """Cập nhật pieces của peer"""
        # piece_info structure:
        # [{
        #    'metainfo_id': str,
        #    'index': int,
        #    'piece': bytes  # Đang lưu nội dung thực của piece
        # }]
        return self._update_one(
            'peers',
            {'peer_id': peer_id},
            {'$set': {'piece_info': piece_info}}
        )

    def get_piece_content(self, info_hash: str, piece_index: int) -> Optional[bytes]:
        """
        Lấy nội dung piece từ database.
        
        Args:
            info_hash: Hash của torrent
            piece_index: Index của piece
            
        Returns:
            bytes: Nội dung của piece hoặc None nếu không tìm thấy
        """
        try:
            # Lấy thông tin peer
            peer = self._find_one('peers', {
                'piece_info': {
                    '$elemMatch': {
                        'metainfo_id': info_hash,
                        'index': piece_index
                    }
                }
            })
            if not peer:
                return None
                
            # Tìm piece trong piece_info
            for piece in peer['piece_info']:
                if (piece['metainfo_id'] == info_hash and 
                    piece['index'] == piece_index):
                    return piece['piece']  # Trả về nội dung piece
                    
            return None
            
        except Exception as e:
            log_event("ERROR", f"Error getting piece content: {e}", "error")
            return None

    def get_piece(self, info_hash: str, piece_index: int) -> Optional[bytes]:
        """
        Alias cho get_piece_content để tương thích ngược
        """
        return self.get_piece_content(info_hash, piece_index)

    def update_peer_connection(self, peer_id: str, ip_address: str, port: int) -> bool:
        """
        Cập nhật thông tin kết nối của peer.
        
        Args:
            peer_id: ID của peer
            ip_address: IP address mới
            port: Port mới
            
        Returns:
            bool: True nếu cập nhật thành công
        """
        try:
            result = self._update_one(
                'peers',
                {'peer_id': peer_id},
                {
                    '$set': {
                        'ip_address': ip_address,
                        'port': port
                    }
                }
            )
            return result
        except Exception as e:
            log_event("ERROR", f"Error updating peer connection: {e}", "error")
            return False 