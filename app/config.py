class Config:
    """Global configuration settings"""
    
    # Network settings
    DEFAULT_PORT = 6881
    TRACKER_PORT = 6969
    TRACKER_HOST = "10.229.11.188"
    
    # MongoDB settings
    DB_URI = "mongodb://localhost:27017/"
    DB_NAME = "bittorrent"
    
    # Collection names
    COLLECTIONS = {
        'PEERS': 'peers',      # Chỉ peers truy cập
        'TORRENTS': 'torrents', # Chỉ tracker truy cập
        'FILES': 'files'       # Chỉ tracker truy cập
    }
    
    # Piece settings
    PIECE_LENGTH = 32 * 1024  # 32KB
    MAX_PIECE_SIZE = 1024 * 1024  # 1MB maximum piece size
    MIN_PIECE_SIZE = 32 * 1024   # 32KB minimum piece size
    PIECE_TIMEOUT = 10  # Timeout cho việc download một piece
    
    # Connection settings
    MAX_PEER_CONNECTIONS = 5  # Số lượng kết nối tối đa cho mỗi peer
    MAX_DOWNLOAD_THREADS = 5   # Số thread download đồng thời
    SOCKET_TIMEOUT = 5        # Timeout cho socket operations
    MAX_RETRIES = 5           # Số lần thử lại khi fail
    
    # Tracker settings
    TRACKER_CLEANUP_INTERVAL = 300  # 5 phút cleanup một lần
    PEER_TIMEOUT = 1800           # 30 phút không hoạt động thì coi như peer dead
    TRACKER_MAX_PEERS = 100       # Số lượng peers tối đa tracker quản lý
    
    # Storage settings
    TORRENT_OUTPUT_DIR = "output/torrents"  # Thư mục lưu file torrent
    DOWNLOAD_OUTPUT_DIR = "output/downloads" # Thư mục lưu file download
    
    # Debug settings
    DEBUG = True
    LOG_LEVEL = "INFO"
    LOG_FILE = "bittorrent.log"

    @staticmethod
    def get_piece_length(file_size: int) -> int:
        """
        Tính toán piece length tối ưu dựa trên kích thước file.
        
        Args:
            file_size: Kích thước file (bytes)
            
        Returns:
            int: Piece length phù hợp
        """
        if file_size < 1024 * 1024:  # < 1MB
            return 1024  # 1KB pieces
        else:
            return 1024 * 16  # 16KB pieces

    @staticmethod
    def validate_piece_length(length: int) -> bool:
        """Validate piece length"""
        return length > 0 and length <= 1024 * 1024  # Max 1MB

    @staticmethod
    def get_download_path(file_name: str) -> str:
        """
        Tạo đường dẫn lưu file download.
        
        Args:
            file_name: Tên file
            
        Returns:
            str: Đường dẫn đầy đủ
        """
        import os
        if not os.path.exists(Config.DOWNLOAD_OUTPUT_DIR):
            os.makedirs(Config.DOWNLOAD_OUTPUT_DIR)
        return os.path.join(Config.DOWNLOAD_OUTPUT_DIR, file_name)

    @staticmethod 
    def get_torrent_path(file_name: str) -> str:
        """
        Tạo đường dẫn lưu file torrent.
        
        Args:
            file_name: Tên file
            
        Returns:
            str: Đường dẫn đầy đủ
        """
        import os
        if not os.path.exists(Config.TORRENT_OUTPUT_DIR):
            os.makedirs(Config.TORRENT_OUTPUT_DIR)
        return os.path.join(Config.TORRENT_OUTPUT_DIR, f"{file_name}.torrent")