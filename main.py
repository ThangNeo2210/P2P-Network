import argparse
import os
import threading
from app.tracker.tracker import Tracker
from app.peer.peer import PeerNode
from app.peer.server import PeerServer
from app.torrent.torrent import TorrentHandler
from app.utils.helpers import log_event
from app.config import Config

def run_tracker(host: str = Config.TRACKER_HOST, port: int = Config.TRACKER_PORT):
    """Run tracker server"""
    tracker = Tracker()
    try:
        log_event("SYSTEM", f"Starting tracker on {host}:{port}", "info")
        tracker.run_peer_server(host, port)
    except KeyboardInterrupt:
        log_event("SYSTEM", "Stopping tracker...", "warning")
    except Exception as e:
        log_event("ERROR", f"Tracker error: {e}", "error")

def run_peer(peer_id: str, host: str, port: int):
    """Run peer node and server"""
    # Initialize peer components
    peer = PeerNode(host, port, peer_id)
    server = PeerServer(host, port, peer_id)
    
    # Start peer server in a separate thread
    server_thread = threading.Thread(target=server.run_peer_server)
    server_thread.daemon = True
    server_thread.start()
    
    log_event("SYSTEM", f"Peer {peer_id} running on {host}:{port}", "info")
    return peer, server

def upload_torrent(file_path: str, peer_id: str):
    """Upload file and create torrent"""
    try:
        tracker = Tracker()
        success = tracker.upload_file(file_path, peer_id)
        if success:
            log_event("SYSTEM", f"Successfully uploaded {file_path}", "success")
        else:
            log_event("ERROR", "Failed to upload file", "error")
    except Exception as e:
        log_event("ERROR", f"Upload error: {e}", "error")

def download_torrent(torrent_file: str, output_path: str, peer_id: str):
    """Download file from torrent"""
    try:
        # Get torrent info
        torrent_handler = TorrentHandler()
        torrent_data = torrent_handler.get_torrent(torrent_file)
        if not torrent_data:
            raise Exception("Failed to get torrent info")
            
        # Get peer list
        peers = torrent_handler.get_peer_list(torrent_data)
        if not peers:
            raise Exception("No peers available")
            
        # Get pieces to download
        piece_indexes = torrent_handler.get_available_pieces(peer_id, torrent_data)
        
        # Start download
        peer = PeerNode(Config.TRACKER_HOST, Config.DEFAULT_PORT, peer_id)
        pieces = peer.request_pieces_from_peers(peers, piece_indexes, torrent_data, [])
        
        # Save file
        from app.torrent.piece import combine_pieces
        if combine_pieces(pieces, output_path):
            log_event("SYSTEM", f"Successfully downloaded to {output_path}", "success")
        else:
            raise Exception("Failed to save file")
            
    except Exception as e:
        log_event("ERROR", f"Download error: {e}", "error")

def main():
    parser = argparse.ArgumentParser(description='BitTorrent Client')
    
    # Main commands
    parser.add_argument('command', choices=['tracker', 'peer', 'upload', 'download'],
                      help='Command to execute')
                      
    # Tracker options
    parser.add_argument('--host', default=Config.TRACKER_HOST,
                      help='Host address')
    parser.add_argument('--port', type=int, default=Config.TRACKER_PORT,
                      help='Port number')
                      
    # Peer options
    parser.add_argument('--peer-id', help='Unique peer ID')
    
    # File options
    parser.add_argument('--file', help='File to upload/download')
    parser.add_argument('--torrent', help='Torrent file')
    parser.add_argument('--output', help='Output path for downloaded file')

    args = parser.parse_args()

    try:
        if args.command == 'tracker':
            run_tracker(args.host, args.port)
            
        elif args.command == 'peer':
            if not args.peer_id:
                raise ValueError("Peer ID required")
            run_peer(args.peer_id, args.host, args.port)
            
            # Keep main thread running
            try:
                while True:
                    threading.Event().wait(1)
            except KeyboardInterrupt:
                log_event("SYSTEM", f"Stopping peer {args.peer_id}...", "warning")
            
        elif args.command == 'upload':
            if not all([args.file, args.peer_id]):
                raise ValueError("File path and peer ID required")
            upload_torrent(args.file, args.peer_id)
            
        elif args.command == 'download':
            if not all([args.torrent, args.output, args.peer_id]):
                raise ValueError("Torrent file, output path and peer ID required")
            download_torrent(args.torrent, args.output, args.peer_id)
            
    except Exception as e:
        log_event("ERROR", f"Error: {e}", "error")
        parser.print_help()

if __name__ == "__main__":
    main() 