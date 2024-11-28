import logging
import time
from datetime import datetime
import colorama
from colorama import Fore, Style
from typing import Optional

# Initialize colorama for colored output
colorama.init()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.FileHandler('bittorrent.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

def log_event(event_type: str, message: str, level: str = "info"):
    """
    Log events with color coding and both console and file output
    
    Args:
        event_type: Type of event (e.g. PEER, TRACKER, ERROR)
        message: Log message
        level: Log level (info, warning, error, success)
    """
    # Color mapping
    colors = {
        "info": Fore.WHITE,
        "warning": Fore.YELLOW,
        "error": Fore.RED,
        "success": Fore.GREEN,
        "debug": Fore.CYAN,
        "start": Fore.MAGENTA
    }
    
    # Get color for level
    color = colors.get(level, Fore.WHITE)
    
    # Format timestamp
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Create colored message for console
    console_msg = f"{color}[{timestamp}] [{event_type}] {message}{Style.RESET_ALL}"
    
    # Create plain message for file
    file_msg = f"[{timestamp}] [{event_type}] {message}"
    
    # Log based on level
    if level == "error":
        #logger.error(file_msg)
        print(console_msg)
    elif level == "warning":
        #logger.warning(file_msg)
        print(console_msg)
    elif level == "debug" and logger.level <= logging.DEBUG:
        #logger.debug(file_msg)
        print(console_msg)
    else:
        #logger.info(file_msg)
        print(console_msg)

def format_size(size: int) -> str:
    """Format size in bytes to human readable format"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024:
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} TB"

def format_time(seconds: float) -> str:
    """Format time duration in seconds to human readable format"""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.1f}m"
    else:
        hours = seconds / 3600
        return f"{hours:.1f}h"

def calculate_speed(bytes_transferred: int, elapsed_time: float) -> float:
    """Calculate transfer speed in bytes per second"""
    if elapsed_time == 0:
        return 0
    return bytes_transferred / elapsed_time

def format_speed(speed: float) -> str:
    """Format speed in bytes/sec to human readable format"""
    return f"{format_size(speed)}/s"

def create_progress_bar(progress: float, width: int = 50) -> str:
    """Create a progress bar string
    
    Args:
        progress: Progress value between 0 and 1
        width: Width of progress bar in characters
        
    Returns:
        Progress bar string like [=====>----] 45%
    """
    filled = int(width * progress)
    bar = '=' * filled + '>' + '-' * (width - filled - 1)
    percent = progress * 100
    return f"[{bar}] {percent:.1f}%"

def validate_peer_id(peer_id: str) -> bool:
    """Validate peer ID format"""
    if not peer_id:
        return False
    if len(peer_id) != 20:
        return False
    return True

def get_file_info(file_path: str) -> Optional[dict]:
    """Get file information including size and modification time"""
    try:
        import os
        stats = os.stat(file_path)
        return {
            'size': stats.st_size,
            'modified': datetime.fromtimestamp(stats.st_mtime),
            'created': datetime.fromtimestamp(stats.st_ctime)
        }
    except Exception as e:
        log_event("ERROR", f"Failed to get file info: {e}", "error")
        return None

def ensure_dir(dir_path: str):
    """Create directory if it doesn't exist"""
    import os
    if not os.path.exists(dir_path):
        os.makedirs(dir_path) 