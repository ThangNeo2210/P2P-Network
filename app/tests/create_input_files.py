import argparse
import os
import random
import string

def generate_random_content(size_kb: int) -> str:
    """Tạo nội dung ngẫu nhiên với kích thước xác định (KB)"""
    chars = string.ascii_letters + string.digits + string.punctuation + ' \n'
    return ''.join(random.choice(chars) for _ in range(size_kb * 1024))

def create_random_files(num_files: int, output_path: str):
    """
    Tạo các file txt với nội dung ngẫu nhiên.
    
    Args:
        num_files: Số lượng file cần tạo
        output_path: Thư mục đặt file
    """
    # Tạo thư mục nếu chưa tồn tại
    if not os.path.exists(output_path):
        os.makedirs(output_path)
        
    for i in range(num_files):
        # Tạo kích thước ngẫu nhiên từ 1KB đến 100KB
        size_kb = random.randint(1, 100)
        
        # Tạo tên file
        filename = f"random_file_{i+1}.txt"
        filepath = os.path.join(output_path, filename)
        
        # Tạo nội dung và ghi file
        content = generate_random_content(size_kb)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
            
        print(f"Created {filename} ({size_kb}KB)")

def main():
    parser = argparse.ArgumentParser(description='Create random text files')
    parser.add_argument('--num_files', type=int, help='Number of files to create')
    parser.add_argument('--path', default='input_files', help='Output directory path')
    
    args = parser.parse_args()
    
    create_random_files(args.num_files, args.path)
    print(f"\nCreated {args.num_files} files in {args.path}")

if __name__ == '__main__':
    main() 