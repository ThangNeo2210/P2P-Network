from tinydb import TinyDB, Query
import json
from typing import Dict, List, Optional
from datetime import datetime
from app.utils.helpers import log_event
from app.config import Config

class Database:
    def __init__(self, db_path: str = Config.DB_PATH):
        self.db = TinyDB(db_path)
        self.peers = self.db.table(Config.DB_TABLES['PEERS'])
        self.torrents = self.db.table(Config.DB_TABLES['TORRENTS'])
        self.files = self.db.table(Config.DB_TABLES['FILES'])

    # Peer operations
    def add_peer(self, peer_data: Dict) -> int:
        """
        Add peer with structure:
        {
            'peer_id': str,
            'ip_address': str,
            'port': int,
            'last_seen': datetime,
            'piece_info': List[Dict],  # [{metainfo_id, index, piece}]
            'total_uploaded': int,
            'total_downloaded': int,
            'failed_uploads': int,
            'successful_uploads': int,
            'network_stats': {
                'upload_bandwidth': float,
                'download_bandwidth': float,
                'latency': float,
                'active_connections': int,
                'cpu_usage': float,
                'success_rate': float,
                'uptime': float,
                'last_update': datetime
            }
        }
        """
        peer_data['last_seen'] = str(datetime.utcnow())
        return self.peers.insert(peer_data)

    # Torrent operations  
    def add_torrent(self, torrent_data: Dict) -> int:
        """
        Add torrent with structure:
        {
            'info_hash': str,
            'info': {
                'name': str,
                'piece_length': int,
                'length': int,
                'pieces': List[bytes]
            },
            'created_at': datetime
        }
        """
        torrent_data['created_at'] = str(datetime.utcnow())
        return self.torrents.insert(torrent_data)

    # File operations
    def add_file(self, file_data: Dict) -> int:
        """
        Add file with structure:
        {
            'file_name': str,
            'metainfo_id': str,  # Reference to Torrent info_hash
            'peers_info': List[Dict],  # [{peer_id, pieces}]
            'created_at': datetime
        }
        """
        file_data['created_at'] = str(datetime.utcnow())
        return self.files.insert(file_data)

    def get_peer(self, peer_id: str) -> Optional[Dict]:
        Peer = Query()
        return self.peers.get(Peer.peer_id == peer_id)

    def get_torrent(self, info_hash: str) -> Optional[Dict]:
        Torrent = Query()
        return self.torrents.get(Torrent.info_hash == info_hash)

    def get_file(self, metainfo_id: str) -> Optional[Dict]:
        File = Query()
        return self.files.get(File.metainfo_id == metainfo_id)

    def update_peer_stats(self, peer_id: str, stats: Dict):
        """Update peer network stats"""
        Peer = Query()
        peer = self.peers.get(Peer.peer_id == peer_id)
        if peer:
            peer['network_stats'].update(stats)
            peer['last_seen'] = str(datetime.utcnow())
            self.peers.update(peer, Peer.peer_id == peer_id)

    def update_file_peers(self, metainfo_id: str, peer_id: str, pieces: List[int]):
        """Update peer's pieces for a file"""
        File = Query()
        file = self.files.get(File.metainfo_id == metainfo_id)
        
        if file:
            peers_info = file['peers_info']
            peer_found = False
            for peer_info in peers_info:
                if peer_info['peer_id'] == peer_id:
                    peer_info['pieces'] = pieces
                    peer_found = True
                    break
            
            if not peer_found:
                peers_info.append({
                    'peer_id': peer_id,
                    'pieces': pieces
                })
                
            self.files.update({'peers_info': peers_info}, File.metainfo_id == metainfo_id)

    def remove_inactive_peers(self, timeout: int = Config.CONNECTION_TIMEOUT):
        """Remove peers that haven't been seen for a while"""
        Peer = Query()
        current_time = datetime.utcnow()
        
        def is_inactive(peer):
            last_seen = datetime.fromisoformat(peer['last_seen'])
            return (current_time - last_seen).seconds > timeout
            
        self.peers.remove(is_inactive)