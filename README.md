## Usage:
1. Run tracker:
    python main.py tracker --host localhost --port 6969
2. Run peer:
    python main.py peer --host localhost --port 6881 --peer_id <peer_id>
3. Upload torrent:
    python main.py upload --file <file_path> --peer_id <peer_id>
4. Download torrent:
    python main.py download --torrent <torrent_file> --output <output_path> --peer_id <peer_id>
