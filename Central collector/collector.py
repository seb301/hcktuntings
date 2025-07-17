# Add Logging Configuration in settings.py
# Set up File Handler

import paramiko
import os
import json
import datetime
from concurrent.futures import ThreadPoolExecutor

# Configuration
hosts = [
    {"name": "web1", "ip": "192.168.1.10", "user": "ubuntu", "logs": ["/var/log/nginx/access.log"]},
    {"name": "app1", "ip": "192.168.1.20", "user": "ubuntu", "logs": ["/home/ubuntu/django/logs/app.log"]},
]
SSH_KEY_PATH = os.path.expanduser("~/.ssh/id_rsa")
DESTINATION_DIR = "./central_logs"
OFFSET_STORE = "./offsets.json"
TIMESTAMP = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M")

# Load existing offsets
if os.path.exists(OFFSET_STORE):
    with open(OFFSET_STORE, 'r') as f:
        offsets = json.load(f)
else:
    offsets = {}

def save_offsets():
    with open(OFFSET_STORE, 'w') as f:
        json.dump(offsets, f, indent=2)

def fetch_incremental_log(host, log_path):
    host_key = f"{host['name']}@{log_path}"
    last_offset = offsets.get(host_key, 0)

    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(host["ip"], username=host["user"], key_filename=SSH_KEY_PATH)
        sftp = ssh.open_sftp()
        remote_file = sftp.file(log_path, "r")
        remote_file_size = remote_file.stat().st_size

        if last_offset >= remote_file_size:
            print(f"⚠️ No new data in {host_key}")
            remote_file.close()
            sftp.close()
            ssh.close()
            return

        # Seek to last read offset
        remote_file.seek(last_offset)
        new_data = remote_file.read().decode("utf-8")

        # Save new data
        filename = os.path.basename(log_path)
        host_dir = os.path.join(DESTINATION_DIR, host['name'])
        os.makedirs(host_dir, exist_ok=True)
        out_file = os.path.join(host_dir, f"{filename}_{TIMESTAMP}.log")

        with open(out_file, "w") as f:
            f.write(new_data)

        # Update offset
        offsets[host_key] = remote_file_size

        print(f"✅ Fetched {remote_file_size - last_offset} bytes from {host_key}")

        remote_file.close()
        sftp.close()
        ssh.close()
    except Exception as e:
        print(f"❌ Failed to fetch {host_key}: {e}")

def process_host(host):
    for log_path in host["logs"]:
        fetch_incremental_log(host, log_path)

def main():
    with ThreadPoolExecutor(max_workers=5) as executor:
        executor.map(process_host, hosts)
    save_offsets()

if __name__ == "__main__":
    main()
