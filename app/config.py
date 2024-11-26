class Config:
    """Global configuration settings"""
    
    # Network settings
    DEFAULT_PORT = 6881
    TRACKER_PORT = 6969
    TRACKER_HOST = "127.0.0.1"
    
    # Database settings
    DB_PATH = "bittorrent.json"
    DB_TABLES = {
        'PEERS': 'peers',
        'TORRENTS': 'torrents',
        'FILES': 'files'
    }
    
    # Piece settings
    PIECE_LENGTH = 256 * 1024  # 256KB default piece size
    MAX_PIECE_SIZE = 1024 * 1024  # 1MB maximum piece size
    MIN_PIECE_SIZE = 32 * 1024   # 32KB minimum piece size
    
    MAX_RETRIES = 3
    
    # Connection settings
    MAX_CONNECTIONS = 50
    CONNECTION_TIMEOUT = 30
    SOCKET_TIMEOUT = 10
    
    # Protocol settings
    PROTOCOL_STRING = "BitTorrent protocol"
    HANDSHAKE_LENGTH = 68
    PEER_ID_LENGTH = 20
    
    # Storage settings
    CACHE_SIZE = 100  # Number of pieces to cache
    STORAGE_PATH = ".torrent_data"
    
    # MongoDB settings
    MONGODB_HOST = "localhost"
    MONGODB_PORT = 27017
    MONGODB_DB = "bittorrent"
    
    # Tracker settings
    TRACKER_CLEANUP_INTERVAL = 300  # 5 minutes
    PEER_TIMEOUT = 1800  # 30 minutes
    
    # Debug settings
    DEBUG = True
    LOG_LEVEL = "INFO"

    @staticmethod
    def get_piece_length(file_size: int) -> int:
        """Calculate optimal piece length based on file size"""
        if file_size < 1024 * 1024:  # < 1MB
            return Config.MIN_PIECE_SIZE
        elif file_size < 10 * 1024 * 1024:  # < 10MB  
            return 64 * 1024  # 64KB
        elif file_size < 100 * 1024 * 1024:  # < 100MB
            return 128 * 1024  # 128KB
        else:
            return Config.PIECE_LENGTH  # Default 256KB

    @staticmethod
    def validate_piece_length(piece_length: int) -> bool:
        """Validate if piece length is within acceptable range"""
        return Config.MIN_PIECE_SIZE <= piece_length <= Config.MAX_PIECE_SIZE 