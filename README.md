## Notes
- Tracker server phải được khởi động trước khi thực hiện các thao tác khác.
- Mỗi peer nên có một ID duy nhất để tránh xung đột.
- File torrent được tạo sẽ lưu trong thư mục `output/torrents/`.
- File download sẽ được lưu trong thư mục `output/downloads/`

## Config
Tất cả các config được lưu trong file `app/config.py`

## MongoDB Setup
Collections:
- `peers`: Lưu thông tin peers và pieces họ đang có
- `torrents`: Lưu metadata của các torrent files
- `files`: Lưu thông tin file và peer distribution

## Tạo dữ liệu test

1. Tạo các file input ngẫu nhiên:
```bash
python -m app.tests.create_input_files --num_files 10 --path input_files
```

<!-- 2. Tạo test data cho peer và lưu vào database:
```bash
# Sử dụng IP mặc định (Config.TRACKER_HOST)
python -m app.tests.create_test_data --peer-id peer_1 --input-dir input_files --port 6881

# Hoặc chỉ định IP cụ thể
python -m app.tests.create_test_data --peer-id peer_1 --input-dir input_files --port 6881 --ip 127.0.0.1
```

Ví dụ tạo test data cho nhiều peers:
```bash
python -m app.tests.create_test_data --peer-id peer_1 --input-dir input_peer_1 --port 6881
python -m app.tests.create_test_data --peer-id peer_2 --input-dir input_peer_2 --port 6882
python -m app.tests.create_test_data --peer-id peer_3 --input-dir input_peer_3 --port 6883
``` -->



## Example Usage

1. **Khởi động tracker**:
```bash
python main.py tracker --host 127.0.0.1 --port 6969
```

2. **Tạo torrent file**:
```bash
# Tạo torrent cho một file
python main.py create --input input/myfile.txt

# Tạo torrent cho tất cả files trong folder
python main.py create --input input_folder/
```

3. **Upload file/folder**:
```bash
# Upload một file
python main.py upload --input input/myfile.txt --peer-id peer1 --peer-port 6881

# Upload tất cả files trong folder
python main.py upload --input input_folder/ --peer-id peer1 --peer-port 6881

# Chỉ định IP
python main.py upload --input input/myfile.txt --peer-id peer1 --peer-port 6881 --peer-host 127.0.0.1
```

4. **Download file**:
   ```bash
   python main.py download --torrent output/torrents/pdf_1.pdf.torrent --output output/downloads/pdf_1.pdf --peer-id peer_2 --peer-port 6882
   ```

5. **Xem danh sách peers**:
```bash
python main.py get --torrent output/torrents/myfile.txt.torrent
```

## Ví dụ thiết lập nhiều peers:
```bash
# Start tracker
python main.py tracker

# Start peer servers
python main.py start-peer --peer-id peer1 --peer-port 6881
python main.py start-peer --peer-id peer2 --peer-port 6882

# If there is not file torrent of it, let create it. It will be saved in output/torrents/
python main.py create --input input/file.txt
# Upload từ peer1
python main.py upload --input input/file.txt --peer-id peer1 --peer-port 6881

# Download từ peer2 
python main.py download --torrent output/torrents/file.txt.torrent --output output/downloads/file.txt --peer-id peer2 --peer-port 6882
```


