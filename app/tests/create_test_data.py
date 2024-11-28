import os
import hashlib
import base64
import argparse
from app.config import Config
from app.torrent.piece import split_file
from app.utils.torrent_utils import generate_info_hash
from app.utils.helpers import log_event
from pymongo import MongoClient

def create_test_data(peer_id: str, input_dir: str, ip: str, port: int):
    try:
        client = MongoClient(Config.DB_URI)
        db = client[Config.DB_NAME]
        log_event("SYSTEM", "Connected to MongoDB successfully", "info")
    except Exception as e:
        log_event("ERROR", f"Failed to connect to MongoDB: {e}", "error")
        return
    
    # Lấy danh sách tất cả các file trong thư mục input
    if not os.path.exists(input_dir):
        log_event("ERROR", f"Input directory not found: {input_dir}", "error")
        return
        
    input_files = [
        os.path.join(input_dir, f) 
        for f in os.listdir(input_dir) 
        if os.path.isfile(os.path.join(input_dir, f))
    ]
    
    if not input_files:
        log_event("ERROR", f"No files found in directory: {input_dir}", "error")
        return
    
    # Tạo peer entry
    peer_data = {
        'peer_id': peer_id,
        'ip_address': ip,
        'port': port,
        'piece_info': []
    }
    
    # Xóa dữ liệu cũ của peer này
    log_event("SYSTEM", "Cleaning up old test data...", "info")
    db.peers.delete_many({'peer_id': peer_id})
    
    # Insert peer
    db.peers.insert_one(peer_data)
    log_event("SYSTEM", f"Created new peer: {peer_id}", "success")
    
    # Xử lý từng file
    for file_path in input_files:
        file_name = os.path.basename(file_path)
        file_length = os.path.getsize(file_path)
        log_event("SYSTEM", f"Processing file: {file_name} ({file_length} bytes)", "info")
            
        # 1. Split file thành pieces
        pieces = split_file(file_path, Config.PIECE_LENGTH)
        if not pieces:
            log_event("ERROR", f"Failed to split file {file_path}", "error")
            continue
            
        log_event("SYSTEM", f"Split file into {len(pieces)} pieces ({Config.PIECE_LENGTH} bytes each)", "info")
        
        # 2. Generate pieces hash
        piece_hashes = [hashlib.sha1(p).digest() for p in pieces]
        concatenated_hashes = b''.join(piece_hashes)
        encoded_hashes = base64.b64encode(concatenated_hashes)
        
        # 3. Generate info hash
        info_hash = generate_info_hash(
            file_name,
            Config.PIECE_LENGTH,
            encoded_hashes,
            file_length
        )
        
        log_event("SYSTEM", f"Generated info hash for {file_name}: {info_hash}", "info")
        
        # 4. Lưu torrent entry
        torrent_data = {
            'info_hash': info_hash,
            'info': {
                'name': file_name,
                'piece_length': Config.PIECE_LENGTH,
                'length': file_length,
                'pieces': encoded_hashes.decode()
            }
        }
        db.torrents.update_one(
            {'info_hash': info_hash},
            {'$set': torrent_data},
            upsert=True
        )
        
        # 5. Lưu/update file entry
        file_data = {
            'file_name': file_name,
            'metainfo_id': info_hash,
            'peers_info': [{
                'peer_id': peer_id,
                'pieces': list(range(len(pieces)))
            }]
        }
        db.files.update_one(
            {'metainfo_id': info_hash},
            {
                '$set': {
                    'file_name': file_name,
                    'metainfo_id': info_hash
                },
                '$addToSet': {
                    'peers_info': {
                        'peer_id': peer_id,
                        'pieces': list(range(len(pieces)))
                    }
                }
            },
            upsert=True
        )
        
        # 6. Lưu nội dung pieces vào peer
        piece_info = [
            {
                'metainfo_id': info_hash,
                'index': i,
                'piece': pieces[i]
            }
            for i in range(len(pieces))
        ]
        
        # Update peer's piece info
        db.peers.update_one(
            {'peer_id': peer_id},
            {'$push': {'piece_info': {'$each': piece_info}}}
        )
        
        log_event("SYSTEM", f"Successfully processed file: {file_name}", "success")
        
    log_event("SYSTEM", "\nTest data creation completed!", "success")
    log_event("SYSTEM", f"Peer ID: {peer_id}", "info")
    log_event("SYSTEM", f"Input directory: {input_dir}", "info")
    log_event("SYSTEM", f"Files processed: {len(input_files)}", "info")
    for file_path in input_files:
        log_event("SYSTEM", f"- {os.path.basename(file_path)}", "info")

def main():
    parser = argparse.ArgumentParser(description='Create test data for BitTorrent')
    parser.add_argument('--peer-id', required=True, help='Peer ID to use')
    parser.add_argument('--input-dir', required=True, help='Directory containing input files')
    parser.add_argument('--port', type=int, default=6881, help='Port number for peer')
    parser.add_argument('--ip', default=Config.TRACKER_HOST, help='IP address for peer')
    
    args = parser.parse_args()
    create_test_data(args.peer_id, args.input_dir, args.ip, args.port)

if __name__ == "__main__":
    main() 