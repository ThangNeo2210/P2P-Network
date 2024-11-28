import os
import sys
import argparse
from typing import Optional, List
from app.config import Config
from app.utils.helpers import log_event
from app.torrent.torrent import TorrentHandler
from app.peer.peer import PeerNode
from app.tracker.tracker import Tracker
import threading
import uuid
import socket
import time

def get_peer_id(input_id: Optional[str] = None) -> str:
    if input_id:
        return input_id
    return str(uuid.uuid4())

def create_torrent(input_path: str) -> List[str]:

    try:
        if not os.path.exists(input_path):
            raise ValueError(f"Input path not found: {input_path}")
            
        created_torrents = []
        torrent_handler = TorrentHandler()

        if os.path.isfile(input_path):
            # Xử lý một file
            file_name = os.path.basename(input_path)
            output_file = Config.get_torrent_path(file_name)
            info_hash = torrent_handler.create_torrent_file(input_path, output_file)
            if info_hash:
                log_event("SYSTEM", f"Created torrent for {file_name}", "success")
                log_event("SYSTEM", f"Info hash: {info_hash}", "info")
                created_torrents.append(output_file)
            
        elif os.path.isdir(input_path):
            # Xử lý tất cả files trong folder
            for file_name in os.listdir(input_path):
                file_path = os.path.join(input_path, file_name)
                if os.path.isfile(file_path):
                    output_file = Config.get_torrent_path(file_name)
                    info_hash = torrent_handler.create_torrent_file(file_path, output_file)
                    if info_hash:
                        log_event("SYSTEM", f"Created torrent for {file_name}", "success")
                        log_event("SYSTEM", f"Info hash: {info_hash}", "info")
                        created_torrents.append(output_file)
                    else:
                        log_event("ERROR", f"Failed to create torrent for {file_name}", "error")

        if not created_torrents:
            raise Exception("No torrent files were created")

        log_event("SYSTEM", f"Created {len(created_torrents)} torrent files", "success")
        return created_torrents
        
    except Exception as e:
        log_event("ERROR", f"Error creating torrent(s): {e}", "error")
        return []

def start_tracker(host: str = Config.TRACKER_HOST, 
                 port: int = Config.TRACKER_PORT) -> Optional[Tracker]:
    try:
        tracker = Tracker()
        
        # Chạy tracker trong thread riêng
        tracker_thread = threading.Thread(
            target=tracker.run_peer_server,
            args=(host, port)
        )
        tracker_thread.daemon = True
        tracker_thread.start()
        
        log_event("SYSTEM", f"Tracker started on {host}:{port}", "success")
        return tracker
        
    except Exception as e:
        log_event("ERROR", f"Error starting tracker: {e}", "error")
        return None

def upload_file(file_path: str, tracker: Tracker, peer_id: Optional[str] = None) -> bool:

    try:
        # Lấy hoặc tạo peer ID
        uploader_id = get_peer_id(peer_id)
        
        # Upload file lên tracker
        if not tracker.upload_file(file_path, uploader_id):
            raise Exception("Failed to upload file to tracker")
            
        log_event("SYSTEM", f"File uploaded successfully by peer {uploader_id}", "success")
        return True
        
    except Exception as e:
        log_event("ERROR", f"Error uploading file: {e}", "error")
        return False

def download_torrent(torrent_file: str, output_path: str, peer_id: Optional[str] = None, host: str = Config.TRACKER_HOST, port: int = Config.DEFAULT_PORT) -> bool:
    """Download file từ torrent"""
    try:
        # Khởi tạo peer
        downloader_id = get_peer_id(peer_id)
        peer = PeerNode(host, port, downloader_id)
        
        # Download file
        if not peer.download_file(torrent_file, output_path):
            raise Exception("Download failed")
            
        log_event("SYSTEM", f"Successfully downloaded to {output_path}", "success")
        return True
            
    except Exception as e:
        log_event("ERROR", f"Download error: {e}", "error")
        return False

def is_tracker_running(host: str = Config.TRACKER_HOST, port: int = Config.TRACKER_PORT) -> bool:

    try:
        # Thử kết nối đến tracker
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except:
        return False

def setup_parser():
    """Thiết lập argument parser"""
    parser = argparse.ArgumentParser(description="BitTorrent Client")
    
    # Main command
    parser.add_argument('command', 
                       choices=['create', 'tracker', 'upload', 'download', 'get', 'start-peer'],
                       help='Command to execute (create: create torrent, tracker: run tracker server, '
                            'upload: upload file, download: download file, get: get peer list, '
                            'start-peer: start peer server)')


    # Tracker options
    tracker_group = parser.add_argument_group('Tracker options')
    tracker_group.add_argument('--host', default=Config.TRACKER_HOST,
                           help='Tracker host address')
    tracker_group.add_argument('--port', type=int, default=Config.TRACKER_PORT,
                           help='Tracker port number')

    # File options
    file_group = parser.add_argument_group('File options')
    file_group.add_argument('--input', 
                           help='Input file or folder path (for create command)')
    file_group.add_argument('--output', help='Output file path')
    file_group.add_argument('--torrent', help='Torrent file path')

    # Peer options
    peer_group = parser.add_argument_group('Peer options')
    peer_group.add_argument('--peer-id', help='Unique peer ID (optional)')
    peer_group.add_argument('--peer-host', default=Config.TRACKER_HOST,
                         help='Peer host address')
    peer_group.add_argument('--peer-port', type=int, default=Config.DEFAULT_PORT,
                         help='Peer port number')

    return parser

def start_peer_server(peer_id: str, host: str, port: int):
    """Khởi động peer server"""
    peer = PeerNode(host, port, peer_id)
    peer.start_peer_server()

def get_peers_for_torrent(torrent_file: str) -> bool:
    """
    Lấy và hiển thị danh sách peers cho một torrent file.
    
    Args:
        torrent_file: Đường dẫn đến file torrent
    """
    try:
        if not os.path.exists(torrent_file):
            raise ValueError(f"Torrent file not found: {torrent_file}")

        # Đọc thông tin torrent
        torrent_handler = TorrentHandler()
        torrent_data = torrent_handler.read_torrent_file(torrent_file)
        if not torrent_data:
            raise ValueError("Failed to read torrent file")

        # Lấy danh sách peers từ tracker
        tracker = Tracker()
        peers = tracker.get_peer_list(torrent_file)
        
        if not peers:
            print("No peers found for this torrent")
            return False

        # Hiển thị thông tin
        print(f"\nPeers for torrent: {torrent_data['info']['name']}")
        print(f"Info hash: {torrent_data['info_hash']}")
        print(f"Found {len(peers)} peers:")
        
        for peer in peers:
            print(f"\nPeer ID: {peer['peer_id']}")
            print(f"Pieces: {len(peer['pieces'])}/{len(torrent_data['info']['pieces'])//20}")
            
        return True

    except Exception as e:
        log_event("ERROR", f"Error getting peers: {e}", "error")
        return False

def main():
    """Main entry point"""
    parser = setup_parser()
    args = parser.parse_args()

    try:
        if args.command == 'create':
            if not args.input:
                raise ValueError("Input file/folder path required for create command")
            created_files = create_torrent(args.input)
            if created_files:
                print("\nCreated torrent files:")
                for torrent_file in created_files:
                    print(f"- {torrent_file}")
            else:
                print("No torrent files were created")

        elif args.command == 'tracker':
            tracker = start_tracker(args.host, args.port)
            if tracker:
                try:
                    while True:
                        time.sleep(1)
                except KeyboardInterrupt:
                    print("\nStopping tracker...")

        elif args.command == 'upload':
            if not args.input:
                raise ValueError("Input file path required for upload command")
            
            if not is_tracker_running(args.host, args.port):
                raise ValueError("Tracker server is not running")
                
            tracker = Tracker()
            upload_file(args.input, tracker, args.peer_id)

        elif args.command == 'download':
            if not args.torrent:
                raise ValueError("Torrent file path required for download command")
            if not args.output:
                raise ValueError("Output path required for download command")
                
            if not is_tracker_running(args.host, args.port):
                raise ValueError("Tracker server is not running")
                
            download_torrent(args.torrent, args.output, args.peer_id, args.peer_host, args.peer_port)

        elif args.command == 'get':
            if not args.torrent:
                raise ValueError("Torrent file path required for get-peers command")
                
            if not is_tracker_running(args.host, args.port):
                raise ValueError("Tracker server is not running")
                
            get_peers_for_torrent(args.torrent)

        elif args.command == 'start-peer':
            if not args.peer_id:
                raise ValueError("Peer ID is required to start peer server")
            start_peer_server(args.peer_id, args.peer_host, args.peer_port)

    except ValueError as e:
        print(f"Error: {str(e)}")
        parser.print_help()
    except Exception as e:
        print(f"Error: {str(e)}")

if __name__ == '__main__':
    main()