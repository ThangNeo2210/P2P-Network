from mongoengine import *
import datetime

class Peer(Document):
    """Peer information in MongoDB"""
    ip_address = StringField(required=True)
    port = IntField(required=True)
    peer_id = StringField(required=True, unique=True)
    last_seen = DateTimeField(default=datetime.datetime.utcnow)
    
    # Piece information
    piece_info = ListField(DictField())  # List of {metainfo_id, index, piece}
    
    meta = {
        'collection': 'peers',
        'indexes': ['peer_id', 'ip_address']
    }

class Torrent(Document):
    """Torrent information in MongoDB"""
    info_hash = StringField(required=True, unique=True)
    info = DictField(required=True)  # {name, piece_length, length, pieces}
    created_at = DateTimeField(default=datetime.datetime.utcnow)
    
    meta = {
        'collection': 'torrents',
        'indexes': ['info_hash']
    }

class File(Document):
    """File information in MongoDB"""
    file_name = StringField(required=True)
    metainfo_id = ObjectIdField(required=True)  # Reference to Torrent
    peers_info = ListField(DictField())  # List of {peer_id, pieces}
    created_at = DateTimeField(default=datetime.datetime.utcnow)
    
    meta = {
        'collection': 'files',
        'indexes': ['file_name', 'metainfo_id']
    } 