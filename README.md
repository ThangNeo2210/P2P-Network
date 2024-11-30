## Notes
- Tracker server phải được khởi động trước khi thực hiện các thao tác khác.
- Mỗi peer nên có một ID duy nhất để tránh xung đột.
- File torrent được tạo sẽ lưu trong thư mục `output/torrents/`.
- File download sẽ được lưu trong thư mục `output/downloads/`
- Mỗi piece chỉ được thông báo download thành công khi đã verify thành công xong.

## Config
Tất cả các config được lưu trong file `app/config.py`

## MongoDB Setup
Tải MongoDB Community Server và cài đặt.
Config của MongoDB được lưu trong file `app/config.py`
```bash
# Default connection string
mongodb://localhost:27017/bittorrent
```

Có 3 Collections:
- `peers`: Lưu thông tin peers và pieces họ đang có
- `torrents`: Lưu metadata của các torrent files
- `files`: Lưu thông tin file và peer distribution

## Example Usage
1. **Tạo các file txt input ngẫu nhiên (để test nếu không có file input):**
--path: Đường dẫn đến thư mục lưu các file txt
```bash
python -m app.tests.create_input_files --num_files 10 --path input_files
```

2. **Khởi động tracker**:
```bash
python main.py tracker --host 127.0.0.1 --port 6969
```

3. **Khởi động peer servers**:
```bash
# Khởi động một hoặc nhiều peer servers từ config file
python main.py start-peer --config peers.json
```

peers.json format:
```json
{
    "peer1": {
        "ip": "127.0.0.1",
        "port": 6881
    },
    "peer2": {
        "ip": "127.0.0.1",
        "port": 6882
    }
}
```

4. **Tạo torrent file**:
```bash
# Tạo torrent cho một file
python main.py create --input input/myfile.txt

# Tạo torrent cho tất cả files trong folder
python main.py create --input input_folder/
```

5. **Upload file/folder**:
```bash
# Upload một file
python main.py upload --input input/myfile.txt --peer-id peer1 --peer-port 6881

# Upload tất cả files trong folder
python main.py upload --input input/ --peer-id peer1 --peer-port 6881

# Chỉ định IP
python main.py upload --input input/myfile.txt --peer-id peer1 --peer-port 6881 --peer-host 127.0.0.1
```

6. **Download file**:
```bash
python main.py download --torrent output/torrents/myfile.txt.torrent --output output/downloads/myfile.txt --peer-id peer2 --peer-port 6882
```

7. **Xem danh sách peers**:
```bash
python main.py get --torrent output/torrents/myfile.txt.torrent
```

## Ví dụ đơn giản:
```bash
# If no input, let create test data
python -m app.tests.create_input_files --num_files 1 --path input

# Start tracker
python main.py tracker

# Start peer servers
python main.py start-peer --config peers.json

# If there is not file torrent of it, let create it. It will be saved in output/torrents/
python main.py create --input input/random_file_1.txt
# Upload từ peer1
python main.py upload --input input/random_file_1.txt --peer-id peer1 --peer-port 6881

# Download từ peer2 
python main.py download --torrent output/torrents/random_file_1.txt.torrent --output output/downloads/random_file_1.txt --peer-id peer2 --peer-port 6882
```

Download sẽ hiển thị thống kê như sau:
```
Download Statistics:
------------------------------------------------------------
Peer ID         Pieces Downloaded    Final Score    
------------------------------------------------------------
peer1           45                   8.50           
peer2           35                   7.20           
peer3           22                   5.80           
------------------------------------------------------------
Total pieces downloaded: 102
Failed attempts: 5
```

