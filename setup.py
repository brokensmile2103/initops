#!/usr/bin/env python3
import os
import sys
import subprocess
import secrets
import re
import datetime
import json
import urllib.request
import urllib.error

VERSION = "1.4.0"
LOCK_FILE            = "/etc/.initops_deployed.lock"
PULSE_CONFIG_FILE    = "/etc/.initops_pulse.conf"
PULSE_SCRIPT_PATH    = "/usr/local/bin/init-server-pulse.sh"
PULSE_CRON_D_PATH    = "/etc/cron.d/initops-server-pulse"
PULSE_DISK_THRESHOLD = 85   # % disk used
PULSE_RAM_THRESHOLD  = 90   # % RAM used
PULSE_CPU_THRESHOLD  = 90   # % per-core load avg (1m)

if os.geteuid() != 0:
    print("\033[1;31m[ERROR]\033[0m Root privileges required.")
    sys.exit(1)

def check_os():
    try:
        with open('/etc/os-release', 'r') as f:
            content = f.read()
        if 'Ubuntu' not in content or '24.04' not in content:
            print("\033[1;31m[ERROR]\033[0m This script requires Ubuntu 24.04 LTS.")
            print("       Detected OS is not supported. Aborting.")
            sys.exit(1)
    except FileNotFoundError:
        print("\033[1;31m[ERROR]\033[0m Cannot detect OS. /etc/os-release not found.")
        sys.exit(1)

def run_cmd(cmd, ignore_error=False):
    """Executes a system shell process silently."""
    try:
        subprocess.run(cmd, shell=True, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except subprocess.CalledProcessError:
        if not ignore_error:
            print(f"\033[1;31m[ERROR]\033[0m Command failed: {cmd}")
        return False

def get_system_resources():
    """Scans hardware assets and assigns the ideal hardware profile."""
    ram_mb = 0
    try:
        with open('/proc/meminfo', 'r') as f:
            for line in f:
                if 'MemTotal' in line:
                    ram_mb = int(line.split()[1]) // 1024
                    break
    except Exception:
        ram_mb = 1024

    cpu_cores = os.cpu_count() or 1

    # 6-tier profile aligned to real VPS RAM sizes
    if ram_mb < 1500:
        profile     = "micro"
        profile_txt = "Micro (< 1.5 GB)"
    elif ram_mb < 3500:
        profile     = "small"
        profile_txt = "Small (1.5 – 3.5 GB)"
    elif ram_mb < 6000:
        profile     = "standard"
        profile_txt = "Standard (3.5 – 6 GB  |  e.g. 4 GB VPS)"
    elif ram_mb < 14000:
        profile     = "medium"
        profile_txt = "Medium (6 – 14 GB  |  e.g. 8/12 GB VPS)"
    elif ram_mb < 24000:
        profile     = "large"
        profile_txt = "Large (14 – 24 GB  |  e.g. 16 GB VPS)"
    else:
        profile     = "xlarge"
        profile_txt = "XLarge (24 GB+  |  e.g. 32 GB+ Dedicated)"

    return cpu_cores, ram_mb, profile, profile_txt

def validate_input(prompt, default_value, pattern=r'^[a-zA-Z0-9_]+$'):
    """Sanitizes user parameters to safeguard internal system files."""
    while True:
        user_input = input(prompt).strip()
        if not user_input:
            return default_value
        if re.match(pattern, user_input):
            return user_input
        print("\033[1;31m[Error]\033[0m Invalid input pattern. Use alphanumeric characters and underscores only.")

def validate_domain(prompt, default_value="_"):
    """Validates domain name input to prevent config injection."""
    domain_pattern = r'^[a-zA-Z0-9._-]+$'
    while True:
        user_input = input(prompt).strip()
        if not user_input:
            return default_value
        if user_input == "_" or re.match(domain_pattern, user_input):
            return user_input
        print("\033[1;31m[Error]\033[0m Invalid domain format. Use alphanumeric characters, dots, and hyphens only.")

def install_packages():
    print("\n\033[1;32m[*] Installing LEMP stack, Certbot & Firewall...\033[0m")
    os.environ["DEBIAN_FRONTEND"] = "noninteractive"

    run_cmd("apt-get update")
    run_cmd("apt-get install -y software-properties-common curl unzip ghostscript gnupg2 ca-certificates lsb-release")

    # Bypass interactive prompts for iptables-persistent
    run_cmd("echo iptables-persistent iptables-persistent/autosave_v4 boolean true | debconf-set-selections")
    run_cmd("echo iptables-persistent iptables-persistent/autosave_v6 boolean true | debconf-set-selections")

    run_cmd("add-apt-repository -y ppa:ondrej/php")
    run_cmd("apt-get update")

    packages = (
        "nginx mariadb-server redis-server "
        "php8.3-fpm php8.3-mysql php8.3-redis php8.3-bcmath php8.3-opcache "
        "php8.3-mbstring php8.3-intl "
        "php8.3-gd php8.3-imagick "
        "php8.3-xml php8.3-xmlrpc "
        "php8.3-curl "
        "php8.3-zip php8.3-soap "
        "php8.3-exif "
        "imagemagick "
        "certbot python3-certbot-nginx "
        "iptables iptables-persistent"
    )
    run_cmd(f"apt-get install -y {packages}")
    print("\033[1;32m -> System packages deployed successfully.\033[0m")

def setup_firewall():
    print("\033[1;32m[*] Configuring Iptables Firewall...\033[0m")
    run_cmd("iptables -I INPUT -p tcp --dport 22 -j ACCEPT")  # SSH
    run_cmd("iptables -I INPUT -p tcp --dport 80 -j ACCEPT")  # HTTP
    run_cmd("iptables -I INPUT -p tcp --dport 443 -j ACCEPT") # HTTPS

    run_cmd("netfilter-persistent save")
    run_cmd("systemctl enable netfilter-persistent")
    print("\033[1;32m -> Firewall ports (22, 80, 443) secured and saved.\033[0m")

def setup_fail2ban():
    print("\033[1;32m[*] Installing and configuring Fail2Ban...\033[0m")

    run_cmd("apt-get install -y fail2ban")

    fail2ban_conf = (
        "[DEFAULT]\n"
        "bantime = 3600\n"
        "findtime = 600\n"
        "maxretry = 5\n"
        "banaction = iptables-multiport\n\n"
        "[sshd]\n"
        "enabled = true\n"
        "port = ssh\n"
        "logpath = %(sshd_log)s\n"
        "backend = %(sshd_backend)s\n"
    )

    with open('/etc/fail2ban/jail.local', 'w') as f:
        f.write(fail2ban_conf)

    run_cmd("systemctl enable fail2ban")
    run_cmd("systemctl restart fail2ban")

    print("\033[1;32m -> Fail2Ban active: SSH brute-force protection enabled.\033[0m")

def apply_tuning(profile, ram_mb, cpu_cores):
    print(f"\033[1;32m[*] Applying performance optimizations for: {profile.upper()}...\033[0m")

    # -------------------------------------------------------------------------
    # 1. Nginx
    # -------------------------------------------------------------------------
    nginx_base = (
        "user www-data;\n"
        "worker_processes auto;\n"
        "worker_cpu_affinity auto;\n"
        "pid /run/nginx.pid;\n"
        "error_log /var/log/nginx/error.log crit;\n"
        "include /etc/nginx/modules-enabled/*.conf;\n"
    )

    if profile == "micro":
        nginx_events   = "worker_rlimit_nofile 16384;\nevents { worker_connections 1024; use epoll; multi_accept on; }\n"
        nginx_buffers  = (
            "    client_body_buffer_size 64k; client_header_buffer_size 16k;\n"
            "    large_client_header_buffers 4 32k; client_max_body_size 128m;\n"
            "    fastcgi_buffering on; fastcgi_buffers 4 16k; fastcgi_buffer_size 16k;\n"
            "    fastcgi_connect_timeout 60; fastcgi_send_timeout 120; fastcgi_read_timeout 120;\n"
        )
        nginx_keepalive   = "    keepalive_timeout 15; keepalive_requests 10000;\n"
        nginx_file_cache  = "    open_file_cache max=10000 inactive=30s; open_file_cache_valid 60s; open_file_cache_min_uses 2; open_file_cache_errors on;\n"
    elif profile == "small":
        nginx_events   = "worker_rlimit_nofile 65535;\nevents { worker_connections 4096; use epoll; multi_accept on; }\n"
        nginx_buffers  = (
            "    client_body_buffer_size 128k; client_header_buffer_size 32k;\n"
            "    large_client_header_buffers 4 64k; client_max_body_size 128m;\n"
            "    fastcgi_buffering on; fastcgi_buffers 8 16k; fastcgi_buffer_size 16k;\n"
            "    fastcgi_connect_timeout 60; fastcgi_send_timeout 120; fastcgi_read_timeout 120;\n"
        )
        nginx_keepalive   = "    keepalive_timeout 20; keepalive_requests 20000;\n"
        nginx_file_cache  = "    open_file_cache max=50000 inactive=30s; open_file_cache_valid 60s; open_file_cache_min_uses 2; open_file_cache_errors on;\n"
    elif profile == "standard":
        nginx_events   = "worker_rlimit_nofile 65535;\nevents { worker_connections 4096; use epoll; multi_accept on; }\n"
        nginx_buffers  = (
            "    client_body_buffer_size 256k; client_header_buffer_size 64k;\n"
            "    large_client_header_buffers 4 128k; client_max_body_size 128m;\n"
            "    fastcgi_buffering on; fastcgi_buffers 8 16k; fastcgi_buffer_size 32k;\n"
            "    fastcgi_connect_timeout 60; fastcgi_send_timeout 120; fastcgi_read_timeout 120;\n"
        )
        nginx_keepalive   = "    keepalive_timeout 25; keepalive_requests 50000;\n"
        nginx_file_cache  = "    open_file_cache max=100000 inactive=30s; open_file_cache_valid 60s; open_file_cache_min_uses 2; open_file_cache_errors on;\n"
    elif profile == "medium":
        nginx_events   = "worker_rlimit_nofile 100000;\nevents { worker_connections 8192; use epoll; multi_accept on; }\n"
        nginx_buffers  = (
            "    client_body_buffer_size 256k; client_header_buffer_size 64k;\n"
            "    large_client_header_buffers 4 256k; client_max_body_size 128m;\n"
            "    fastcgi_buffering on; fastcgi_buffers 16 16k; fastcgi_buffer_size 32k;\n"
            "    fastcgi_connect_timeout 60; fastcgi_send_timeout 120; fastcgi_read_timeout 120;\n"
        )
        nginx_keepalive   = "    keepalive_timeout 30; keepalive_requests 100000;\n"
        nginx_file_cache  = "    open_file_cache max=200000 inactive=20s; open_file_cache_valid 30s; open_file_cache_min_uses 2; open_file_cache_errors on;\n"
    elif profile == "large":
        nginx_events   = "worker_rlimit_nofile 200000;\nevents { worker_connections 16384; use epoll; multi_accept on; }\n"
        nginx_buffers  = (
            "    client_body_buffer_size 512k; client_header_buffer_size 128k;\n"
            "    large_client_header_buffers 4 512k; client_max_body_size 128m;\n"
            "    fastcgi_buffering on; fastcgi_buffers 32 16k; fastcgi_buffer_size 64k;\n"
            "    fastcgi_connect_timeout 60; fastcgi_send_timeout 120; fastcgi_read_timeout 120;\n"
        )
        nginx_keepalive   = "    keepalive_timeout 30; keepalive_requests 200000;\n"
        nginx_file_cache  = "    open_file_cache max=350000 inactive=20s; open_file_cache_valid 30s; open_file_cache_min_uses 2; open_file_cache_errors on;\n"
    else:  # xlarge
        nginx_events   = "worker_rlimit_nofile 300000;\nevents { worker_connections 16384; use epoll; multi_accept on; }\n"
        nginx_buffers  = (
            "    client_body_buffer_size 512k; client_header_buffer_size 128k;\n"
            "    large_client_header_buffers 4 512k; client_max_body_size 128m;\n"
            "    fastcgi_buffering on; fastcgi_buffers 32 16k; fastcgi_buffer_size 64k;\n"
            "    fastcgi_connect_timeout 60; fastcgi_send_timeout 120; fastcgi_read_timeout 120;\n"
        )
        nginx_keepalive   = "    keepalive_timeout 30; keepalive_requests 200000;\n"
        nginx_file_cache  = "    open_file_cache max=500000 inactive=30s; open_file_cache_valid 60s; open_file_cache_min_uses 2; open_file_cache_errors on;\n"

    nginx_http = (
        "http {\n"
        "    limit_conn_zone $binary_remote_addr zone=conn_limit_per_ip:10m;\n"
        "    limit_req_zone $binary_remote_addr zone=req_limit_per_ip:10m rate=10r/s;\n"
        "    sendfile on; tcp_nopush on; tcp_nodelay on;\n"
        "    types_hash_max_size 2048; server_tokens off;\n"
        "    reset_timedout_connection on;\n"
        "    include /etc/nginx/mime.types; default_type application/octet-stream;\n"
        "    access_log off;\n"
        "    ssl_protocols TLSv1.2 TLSv1.3; ssl_prefer_server_ciphers on;\n"
        "    ssl_session_cache shared:SSL:10m; ssl_session_timeout 10m;\n"
        + nginx_keepalive
        + nginx_file_cache
        + "    gzip on; gzip_static on; gzip_vary on; gzip_proxied any;\n"
        "    gzip_comp_level 5; gzip_min_length 1024; gzip_http_version 1.1;\n"
        "    gzip_types text/plain text/css application/json application/javascript\n"
        "               application/xml image/svg+xml font/ttf font/otf application/font-woff2;\n"
        + nginx_buffers
        + "    include /etc/nginx/conf.d/*.conf;\n"
        "    include /etc/nginx/sites-enabled/*;\n"
        "}\n"
    )

    with open('/etc/nginx/nginx.conf', 'w') as f:
        f.write(nginx_base + nginx_events + nginx_http)

    # -------------------------------------------------------------------------
    # 2. PHP-FPM pool
    # -------------------------------------------------------------------------
    fpm_pool_conf = "/etc/php/8.3/fpm/pool.d/z_custom_pm.conf"

    if profile == "micro":
        fpm_conf = (
            "[www]\npm = dynamic\n"
            "pm.max_children = 3\npm.start_servers = 1\n"
            "pm.min_spare_servers = 1\npm.max_spare_servers = 2\n"
            "pm.max_requests = 200\npm.process_idle_timeout = 10s\n"
        )
    elif profile == "small":
        fpm_conf = (
            "[www]\npm = dynamic\n"
            "pm.max_children = 6\npm.start_servers = 2\n"
            "pm.min_spare_servers = 2\npm.max_spare_servers = 4\n"
            "pm.max_requests = 500\npm.process_idle_timeout = 10s\n"
        )
    elif profile == "standard":
        # 4 GB VPS — headroom for OS + MySQL + Redis; ~12 PHP workers fits well
        fpm_conf = (
            "[www]\npm = dynamic\n"
            "pm.max_children = 12\npm.start_servers = 3\n"
            "pm.min_spare_servers = 3\npm.max_spare_servers = 6\n"
            "pm.max_requests = 500\npm.process_idle_timeout = 10s\n"
        )
    elif profile == "medium":
        fpm_conf = (
            "[www]\npm = dynamic\n"
            "pm.max_children = 24\npm.start_servers = 6\n"
            "pm.min_spare_servers = 6\npm.max_spare_servers = 12\n"
            "pm.max_requests = 500\npm.process_idle_timeout = 10s\n"
        )
    elif profile == "large":
        fpm_conf = (
            "[www]\npm = dynamic\n"
            "pm.max_children = 48\npm.start_servers = 12\n"
            "pm.min_spare_servers = 10\npm.max_spare_servers = 24\n"
            "pm.max_requests = 500\npm.process_idle_timeout = 10s\n"
        )
    else:  # xlarge
        fpm_conf = (
            "[www]\npm = dynamic\n"
            "pm.max_children = 96\npm.start_servers = 24\n"
            "pm.min_spare_servers = 16\npm.max_spare_servers = 48\n"
            "pm.max_requests = 500\npm.process_idle_timeout = 10s\n"
        )

    with open(fpm_pool_conf, 'w') as f:
        f.write(fpm_conf)

    # Named explicitly so it never collides with user-managed opcache config files
    php_ini_dropin = "/etc/php/8.3/fpm/conf.d/99-initops-runtime.ini"

    if profile == "micro":
        mem_limit = "128M"
    elif profile in ("small", "standard"):
        mem_limit = "256M"
    elif profile in ("medium", "large"):
        mem_limit = "512M"
    else:  # xlarge
        mem_limit = "1024M"

    php_tuning = (
        f"memory_limit = {mem_limit}\n"
        "post_max_size = 128M\n"
        "upload_max_filesize = 128M\n"
        "max_file_uploads = 120\n"
        "max_execution_time = 120\n"
        "max_input_time = 120\n"
        "max_input_vars = 3000\n"
        "default_socket_timeout = 60\n"
        "expose_php = Off\n"
    )

    with open(php_ini_dropin, 'w') as f:
        f.write(php_tuning)

    # -------------------------------------------------------------------------
    # 3. Redis
    # -------------------------------------------------------------------------
    redis_conf_path = "/etc/redis/redis.conf"
    if os.path.exists(redis_conf_path):
        with open(redis_conf_path, 'r') as f:
            r = f.read()

        r = r.replace("# unixsocket /run/redis/redis-server.sock", "unixsocket /var/run/redis/redis.sock")
        r = r.replace("# unixsocketperm 700", "unixsocketperm 770")

        r = re.sub(r'^save\s+\d+\s+\d+', '# save ""', r, flags=re.MULTILINE)
        r = re.sub(r'^save\s+""', 'save ""', r, flags=re.MULTILINE)
        r = re.sub(r'^(dbfilename\s+dump\.rdb)', '# \\1', r, flags=re.MULTILINE)
        r = re.sub(r'^appendonly\s+yes', 'appendonly no', r, flags=re.MULTILINE)

        r = re.sub(r'\n# --- InitOps tuning ---\n.*', '', r, flags=re.DOTALL)

        if profile == "micro":
            redis_extra = (
                "\n# --- InitOps tuning ---\n"
                "tcp-backlog 128\ntimeout 300\ntcp-keepalive 300\nloglevel warning\n"
                "maxmemory 128mb\nmaxmemory-policy allkeys-lru\nmaxmemory-samples 5\n"
                "lazyfree-lazy-eviction yes\nlazyfree-lazy-expire yes\nlazyfree-lazy-server-del yes\n"
                "activerehashing yes\nhz 10\n"
            )
        elif profile == "small":
            redis_extra = (
                "\n# --- InitOps tuning ---\n"
                "tcp-backlog 511\ntimeout 300\ntcp-keepalive 300\nloglevel warning\n"
                "maxmemory 384mb\nmaxmemory-policy allkeys-lru\nmaxmemory-samples 10\n"
                "lazyfree-lazy-eviction yes\nlazyfree-lazy-expire yes\nlazyfree-lazy-server-del yes\n"
                "activerehashing yes\nhz 15\n"
            )
        elif profile == "standard":
            redis_extra = (
                "\n# --- InitOps tuning ---\n"
                "tcp-backlog 511\ntimeout 300\ntcp-keepalive 300\nloglevel warning\n"
                "maxmemory 512mb\nmaxmemory-policy allkeys-lru\nmaxmemory-samples 10\n"
                "lazyfree-lazy-eviction yes\nlazyfree-lazy-expire yes\nlazyfree-lazy-server-del yes\n"
                "activerehashing yes\nhz 15\n"
            )
        elif profile == "medium":
            redis_extra = (
                "\n# --- InitOps tuning ---\n"
                "tcp-backlog 65536\ntimeout 300\ntcp-keepalive 300\nloglevel warning\n"
                "maxmemory 2gb\nmaxmemory-policy allkeys-lru\nmaxmemory-samples 10\nmaxclients 50000\n"
                "lazyfree-lazy-eviction yes\nlazyfree-lazy-expire yes\nlazyfree-lazy-server-del yes\n"
                "activerehashing yes\nhz 15\n"
            )
        elif profile == "large":
            redis_extra = (
                "\n# --- InitOps tuning ---\n"
                "tcp-backlog 65536\ntimeout 300\ntcp-keepalive 300\nloglevel warning\n"
                "maxmemory 4gb\nmaxmemory-policy allkeys-lru\nmaxmemory-samples 10\nmaxclients 100000\n"
                "lazyfree-lazy-eviction yes\nlazyfree-lazy-expire yes\nlazyfree-lazy-server-del yes\n"
                "activerehashing yes\nhz 15\n"
            )
        else:  # xlarge
            redis_extra = (
                "\n# --- InitOps tuning ---\n"
                "tcp-backlog 65536\ntimeout 300\ntcp-keepalive 300\nloglevel warning\n"
                "maxmemory 8gb\nmaxmemory-policy allkeys-lru\nmaxmemory-samples 10\nmaxclients 100000\n"
                "lazyfree-lazy-eviction yes\nlazyfree-lazy-expire yes\nlazyfree-lazy-server-del yes\n"
                "activerehashing yes\nhz 15\n"
            )

        with open(redis_conf_path, 'w') as f:
            f.write(r + redis_extra)

        run_cmd("usermod -aG redis www-data")
        os.makedirs("/var/run/redis", exist_ok=True)
        run_cmd("chown redis:redis /var/run/redis && chmod 775 /var/run/redis")

    # -------------------------------------------------------------------------
    # 4. MariaDB
    # -------------------------------------------------------------------------
    buffer_pool_mb = int(ram_mb * 0.45)

    if profile == "micro":
        buffer_pool_mb   = min(buffer_pool_mb, 256)
        buffer_pool_str  = f"{buffer_pool_mb}M"
        innodb_instances = 1
        innodb_log_size  = "32M";  innodb_log_buf = "8M"
        innodb_io_cap    = 200;    max_conn = 50
        toc = 128;  tdc = 128;  thread_cache = 4
        tmp_tbl = ""
        join_buf = "1M"; sort_buf = "1M"; rnd_buf = "512k"
    elif profile == "small":
        buffer_pool_mb   = min(buffer_pool_mb, 512)
        buffer_pool_str  = f"{buffer_pool_mb}M"
        innodb_instances = 1
        innodb_log_size  = "64M";  innodb_log_buf = "16M"
        innodb_io_cap    = 400;    max_conn = 100
        toc = 256;  tdc = 256;  thread_cache = 8
        tmp_tbl = ""
        join_buf = "2M"; sort_buf = "2M"; rnd_buf = "1M"
    elif profile == "standard":
        # ~45% of 4 GB ≈ 1.8 GB — reasonable, leaves plenty for OS + Redis + PHP
        buffer_pool_mb   = min(buffer_pool_mb, 1536)
        buffer_pool_str  = f"{buffer_pool_mb}M"
        innodb_instances = 1
        innodb_log_size  = "128M"; innodb_log_buf = "32M"
        innodb_io_cap    = 600;    max_conn = 150
        toc = 512;  tdc = 512;  thread_cache = 16
        tmp_tbl = "tmp_table_size = 64M\nmax_heap_table_size = 64M\n"
        join_buf = "2M"; sort_buf = "2M"; rnd_buf = "1M"
    elif profile == "medium":
        buffer_pool_mb   = min(buffer_pool_mb, 4096)
        buffer_pool_str  = f"{buffer_pool_mb}M"
        innodb_instances = 2
        innodb_log_size  = "256M"; innodb_log_buf = "64M"
        innodb_io_cap    = 800;    max_conn = 300
        toc = 1024; tdc = 1024; thread_cache = 64
        tmp_tbl = "tmp_table_size = 128M\nmax_heap_table_size = 128M\n"
        join_buf = "2M"; sort_buf = "2M"; rnd_buf = "1M"
    elif profile == "large":
        bp_gb            = max(1, min(buffer_pool_mb, 7168) // 1024)
        buffer_pool_str  = f"{bp_gb}G"
        innodb_instances = min(cpu_cores, 8)
        innodb_log_size  = "512M"; innodb_log_buf = "128M"
        innodb_io_cap    = 1500;   max_conn = 400
        toc = 2048; tdc = 2048; thread_cache = 96
        tmp_tbl = "tmp_table_size = 256M\nmax_heap_table_size = 256M\n"
        join_buf = "2M"; sort_buf = "2M"; rnd_buf = "1M"
    else:  # xlarge
        bp_gb            = max(1, buffer_pool_mb // 1024)
        buffer_pool_str  = f"{bp_gb}G"
        innodb_instances = min(cpu_cores, 16)
        innodb_log_size  = "1G";   innodb_log_buf = "256M"
        innodb_io_cap    = 2000;   max_conn = 600
        toc = 4096; tdc = 4096; thread_cache = 128
        tmp_tbl = "tmp_table_size = 256M\nmax_heap_table_size = 256M\n"
        join_buf = "2M"; sort_buf = "2M"; rnd_buf = "1M"

    mysql_config = (
        "[mysqld]\n"
        "bind_address = 127.0.0.1\n"
        "connect_timeout = 10\n"
        "wait_timeout = 300\n"
        "interactive_timeout = 300\n"
        "query_cache_type = 0\n"
        "query_cache_size = 0\n"
        "default_storage_engine = InnoDB\n"
        "performance_schema = OFF\n"
        f"innodb_buffer_pool_size = {buffer_pool_str}\n"
        f"innodb_buffer_pool_instances = {innodb_instances}\n"
        f"innodb_log_file_size = {innodb_log_size}\n"
        f"innodb_log_buffer_size = {innodb_log_buf}\n"
        "innodb_flush_log_at_trx_commit = 2\n"
        "innodb_flush_method = O_DIRECT\n"
        f"innodb_io_capacity = {innodb_io_cap}\n"
        f"innodb_io_capacity_max = {innodb_io_cap * 2}\n"
        "innodb_read_io_threads = 4\n"
        "innodb_write_io_threads = 4\n"
        "innodb_file_per_table = 1\n"
        "innodb_stats_on_metadata = 0\n"
        f"max_connections = {max_conn}\n"
        f"table_open_cache = {toc}\n"
        f"table_definition_cache = {tdc}\n"
        f"thread_cache_size = {thread_cache}\n"
        + (tmp_tbl if tmp_tbl else "")
        + f"join_buffer_size = {join_buf}\n"
        f"sort_buffer_size = {sort_buf}\n"
        f"read_rnd_buffer_size = {rnd_buf}\n"
        "slow_query_log = 1\n"
        "long_query_time = 1\n"
        "log_queries_not_using_indexes = 0\n"
        "skip_log_bin\n"
        "skip_name_resolve\n"
        "character_set_server = utf8mb4\n"
        "collation_server = utf8mb4_unicode_ci\n"
    )

    os.makedirs("/etc/mysql/conf.d/", exist_ok=True)
    mysql_custom_path = "/etc/mysql/conf.d/z_custom_optimize.cnf"
    with open(mysql_custom_path, 'w') as f:
        f.write(mysql_config)

    # -------------------------------------------------------------------------
    # 5. Pre-flight config validation
    # -------------------------------------------------------------------------
    print("\n\033[1;34m[*] Validating configurations...\033[0m")

    php_check = subprocess.run(
        "php-fpm8.3 -t", shell=True,
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
    )
    if php_check.returncode != 0:
        print("\033[1;31m[CONFIG ERROR]\033[0m PHP-FPM validation failed:")
        print(php_check.stderr.decode())
        sys.exit(1)

    nginx_check = subprocess.run(
        "nginx -t", shell=True,
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
    )
    if nginx_check.returncode != 0:
        print("\033[1;31m[CONFIG ERROR]\033[0m Nginx validation failed:")
        print(nginx_check.stderr.decode())
        sys.exit(1)

    # -------------------------------------------------------------------------
    # 6. Restart & health check
    # -------------------------------------------------------------------------
    run_cmd("systemctl daemon-reload")

    services = {
        "redis-server": "Redis",
        "mariadb":      "MariaDB",
        "php8.3-fpm":   "PHP-FPM",
        "nginx":        "Nginx",
    }

    for svc, name in services.items():
        print(f" -> Restarting {name}...")
        run_cmd(f"systemctl restart {svc}")
        status = subprocess.run(f"systemctl is-active --quiet {svc}", shell=True)
        if status.returncode != 0:
            print(f"\033[1;31m[SERVICE ERROR]\033[0m {name} failed to start. "
                  f"Check: journalctl -u {svc}")
            sys.exit(1)

    print("\033[1;32m -> All services optimized and verified healthy.\033[0m")

def deploy_wordpress(domain, db_name, db_user, db_prefix):
    print("\n\033[1;32m[*] Deploying WordPress...\033[0m")

    wp_path = "/var/www/html"
    os.makedirs(wp_path, exist_ok=True)
    os.chdir(wp_path)

    run_cmd("curl -sSL https://raw.githubusercontent.com/wp-cli/builds/gh-pages/phar/wp-cli.phar -o /usr/local/bin/wp")
    run_cmd("chmod +x /usr/local/bin/wp")
    run_cmd("wp core download --path=/var/www/html --allow-root")

    db_pass = secrets.token_urlsafe(20)

    run_cmd(f"mysql -u root -e \"CREATE DATABASE IF NOT EXISTS \\`{db_name}\\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;\"")
    run_cmd(f"mysql -u root -e \"CREATE USER IF NOT EXISTS '{db_user}'@'localhost' IDENTIFIED BY '{db_pass}';\"")
    run_cmd(f"mysql -u root -e \"GRANT ALL PRIVILEGES ON \\`{db_name}\\`.* TO '{db_user}'@'localhost';\"")
    run_cmd("mysql -u root -e \"FLUSH PRIVILEGES;\"")

    run_cmd(
        f"wp config create "
        f"--dbname={db_name} --dbuser={db_user} --dbpass={db_pass} "
        f"--dbprefix={db_prefix} "
        f"--dbhost=\":/run/mysqld/mysqld.sock\" "
        f"--dbcharset=utf8mb4 "
        f"--dbcollate=utf8mb4_unicode_ci "
        f"--path=/var/www/html --allow-root"
    )

    redis_prefix = f"io_{secrets.token_hex(4)}:"

    redis_wp_inject = (
        "\n/* Redis Object Cache — Unix Socket */\n"
        "define( 'WP_REDIS_SCHEME', 'unix' );\n"
        "define( 'WP_REDIS_PATH', '/var/run/redis/redis.sock' );\n"
        "define( 'WP_REDIS_TIMEOUT', 1 );\n"
        "define( 'WP_REDIS_READ_TIMEOUT', 1 );\n"
        f"define( 'WP_REDIS_PREFIX', '{redis_prefix}' );\n"
        "\n/* WordPress Performance */\n"
        "define( 'WP_POST_REVISIONS', 5 );\n"
        "define( 'AUTOSAVE_INTERVAL', 120 );\n"
        "define( 'EMPTY_TRASH_DAYS', 7 );\n"
        "define( 'DISALLOW_FILE_EDIT', true );\n"
        "define( 'DISABLE_WP_CRON', true );\n"
    )

    stop_marker = "/* That's all, stop editing!"
    wp_config_path = "/var/www/html/wp-config.php"
    try:
        with open(wp_config_path, 'r') as f:
            content = f.read()
        if stop_marker in content:
            content = content.replace(stop_marker, redis_wp_inject + stop_marker)
        else:
            content += redis_wp_inject
        with open(wp_config_path, 'w') as f:
            f.write(content)
    except Exception as e:
        print(f"\033[1;31m[ERROR]\033[0m Failed to patch wp-config.php: {e}")
        sys.exit(1)

    # Create empty placeholder to prevent Nginx boot crashes before plugins generate it
    run_cmd("touch /var/www/html/nginx.conf")

    server_name = domain if domain != '_' else '_'
    nginx_vhost = f"""server {{
    listen 80;
    listen [::]:80;
    server_name {server_name};
    root /var/www/html;
    index index.php index.html index.htm;
    client_max_body_size 128m;

    location / {{
        limit_conn conn_limit_per_ip 10;
        limit_req zone=req_limit_per_ip burst=20 nodelay;
        try_files $uri $uri/ /index.php?$args;
    }}

    location ~ \\.php$ {{
        include snippets/fastcgi-php.conf;
        fastcgi_pass unix:/run/php/php8.3-fpm.sock;
        fastcgi_param SCRIPT_FILENAME $document_root$fastcgi_script_name;
        include fastcgi_params;
        fastcgi_hide_header X-Powered-By;
    }}

    location ~* \\.(js|css|png|jpg|jpeg|gif|ico|svg|webp|woff|woff2|ttf|otf|eot)$ {{
        expires 1y;
        add_header Cache-Control "public, immutable";
        log_not_found off;
        access_log off;
    }}

    location ~ /\\.(?:ht|git|svn) {{ deny all; }}
    location ~* wp-config\\.php {{ deny all; }}
    location ~* /(?:uploads|files)/.*\\.php$ {{ deny all; }}

    location = /xmlrpc.php {{ deny all; }}

    include /var/www/html/nginx.conf;
}}"""

    with open('/etc/nginx/sites-available/wordpress', 'w') as f:
        f.write(nginx_vhost)

    if os.path.exists('/etc/nginx/sites-enabled/default'):
        os.remove('/etc/nginx/sites-enabled/default')
    if not os.path.exists('/etc/nginx/sites-enabled/wordpress'):
        os.symlink('/etc/nginx/sites-available/wordpress', '/etc/nginx/sites-enabled/wordpress')

    print(" -> Finalizing permissions for /var/www/html...")
    run_cmd("chown -R www-data:www-data /var/www/html")
    run_cmd("find /var/www/html -type d -exec chmod 755 {} \\;")
    run_cmd("find /var/www/html -type f -exec chmod 644 {} \\;")
    run_cmd("chmod 640 /var/www/html/wp-config.php")

    run_cmd("systemctl reload nginx")
    return db_pass

def setup_system_cron():
    print("\033[1;32m[*] Configuring System Cron for WordPress...\033[0m")

    cron_job    = "* * * * * flock -n /tmp/wp-cron.lock wp cron event run --due-now --path=/var/www/html --quiet > /dev/null 2>&1\n"
    cron_marker = "# wp-cron managed by InitOps"

    result = subprocess.run(
        "crontab -u www-data -l",
        shell=True, capture_output=True, text=True
    )
    existing = result.stdout if result.returncode == 0 else ""

    if "wp cron event run" in existing:
        print("\033[1;32m -> System Cron already configured, skipping.\033[0m")
        return

    new_crontab = existing.rstrip("\n") + f"\n{cron_marker}\n{cron_job}"

    proc = subprocess.run(
        "crontab -u www-data -",
        shell=True, input=new_crontab, text=True,
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
    )
    if proc.returncode != 0:
        print(f"\033[1;31m[ERROR]\033[0m Failed to set crontab: {proc.stderr.strip()}")
        sys.exit(1)

    print("\033[1;32m -> System Cron configured: WP-Cron runs every minute via www-data.\033[0m")

def print_help_menu():
    print("\n\033[1;36m--- Configuration File Locations ---\033[0m")
    print(" Nginx Main Config: /etc/nginx/nginx.conf")
    print(" Nginx Vhost:       /etc/nginx/sites-available/wordpress")
    print(" Plugin Nginx Rules:/var/www/html/nginx.conf")
    print(" PHP-FPM Pool:      /etc/php/8.3/fpm/pool.d/z_custom_pm.conf")
    print(" PHP INI Tuning:    /etc/php/8.3/fpm/conf.d/99-initops-runtime.ini")
    print(" OPcache Config:    /etc/php/8.3/fpm/conf.d/  (manage separately)")
    print(" MariaDB Tuning:    /etc/mysql/conf.d/z_custom_optimize.cnf")
    print(" Redis Config:      /etc/redis/redis.conf")
    print(" WP Config:         /var/www/html/wp-config.php")
    print(" System Cron:       crontab -u www-data -l")
    print("-" * 60)
    print(" \033[1;33mTo install SSL Certificate (HTTPS):\033[0m")
    print(" 1. Ensure your domain points to this server's IP address.")
    print(" 2. Run this command: certbot --nginx")
    print("-" * 60)
    print("Press Enter to return to the main menu...")
    input()

def change_domain():
    """Extracts old domain from Nginx for display, fetches the exact 'home' option from DB as the Source of Truth, and migrates."""
    vhost_path = '/etc/nginx/sites-available/wordpress'
    wp_path = '/var/www/html'

    os.system('clear')
    print("\033[1;36m" + "=" * 60)
    print("              Change Domain & Renew SSL                      ")
    print("=" * 60 + "\033[0m")

    # -------------------------------------------------------------------------
    # STEP 1: Analyze Nginx Vhost & Fetch Absolute Source of Truth from WP DB
    # -------------------------------------------------------------------------
    try:
        with open(vhost_path, 'r') as f:
            vhost_content = f.read()
    except FileNotFoundError:
        print(f"\033[1;31m[ERROR]\033[0m Vhost file not found: {vhost_path}")
        print("Please run Option [1] to deploy WordPress first.")
        print("\nPress Enter to return to the main menu...")
        input()
        return

    # Extract domain from Nginx just for informational display
    match = re.search(r'server_name\s+([^; \t\n]+)', vhost_content)
    nginx_domain = match.group(1).strip() if match else "_"

    # Fetching the sovereign source of truth from database
    print("\033[1;34m[*] Querying WordPress database for current URL...\033[0m")
    db_query = subprocess.run(
        f"wp option get home --path={wp_path} --allow-root", 
        shell=True, capture_output=True, text=True
    )
    
    # Clean the output from DB
    wp_old_url = db_query.stdout.strip() if db_query.returncode == 0 else ""

    # Smart Fallback if DB is unreachable or empty
    if not wp_old_url:
        if nginx_domain != "_":
            wp_old_url = f"https://{nginx_domain}"
            print(f" -> \033[1;33m[NOTE]\033[0m DB query failed. Using Nginx fallback URL.")
        else:
            wp_old_url = ""

    # Display findings to user
    print("\033[1;32m[*] System configuration analysis:\033[0m")
    if wp_old_url:
        print(f" -> Current active WP URL (from DB): \033[1;36m{wp_old_url}\033[0m")
    else:
        print(" -> Current active WP URL: \033[1;33mNot configured / Raw IP\033[0m")
    print(f" -> Current Nginx server_name: \033[1;35m{nginx_domain}\033[0m")
    print("-" * 60)

    print("\033[1;33m[!] WARNING:")
    print("    This will overwrite the Nginx vhost server_name, run Certbot for SSL,")
    print("    and perform a strict Search & Replace on the WordPress database.\033[0m")
    
    confirm = input("\nType 'yes' to proceed or press Enter to cancel: ").strip().lower()
    if confirm != "yes":
        print("Cancelled. No changes made.")
        print("\nPress Enter to return to the main menu...")
        input()
        return

    # User inputs the new domain
    new_domain = validate_domain("\n-> Enter your NEW domain (e.g. newsite.com): ")
    if not new_domain or new_domain == "_":
        print("\033[1;31m[ERROR]\033[0m A real domain name is required for SSL. Aborting.")
        print("\nPress Enter to return to the main menu...")
        input()
        return

    new_url = f"https://{new_domain}"

    # Prevent running if old url matches new url
    if wp_old_url.rstrip('/') == new_url.rstrip('/'):
        print("\033[1;31m[ERROR]\033[0m The new domain is identical to the currently configured domain!")
        print("\nPress Enter to return to the main menu...")
        input()
        return

    # -------------------------------------------------------------------------
    # STEP 2: Update Nginx Vhost to the New Domain
    # -------------------------------------------------------------------------
    print(f"\n\033[1;32m[*] Updating Nginx vhost → server_name: {new_domain}\033[0m")
    updated_vhost = re.sub(
        r'(server_name\s+)[^\s;]+(\s*;)',
        rf'\g<1>{new_domain}\2',
        vhost_content
    )

    with open(vhost_path, 'w') as f:
        f.write(updated_vhost)

    # Validate Nginx configuration before reloading
    nginx_check = subprocess.run(
        "nginx -t", shell=True,
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
    )
    if nginx_check.returncode != 0:
        print("\033[1;31m[CONFIG ERROR]\033[0m Nginx validation failed after domain update:")
        print(nginx_check.stderr.decode())
        print("Reverting vhost to previous state...")
        with open(vhost_path, 'w') as f:
            f.write(vhost_content)
        print("\nPress Enter to return to the main menu...")
        input()
        return

    run_cmd("systemctl reload nginx")
    print("\033[1;32m -> Nginx reloaded with new domain.\033[0m")

    # -------------------------------------------------------------------------
    # STEP 3: Issue New SSL Certificate via Certbot
    # -------------------------------------------------------------------------
    print(f"\n\033[1;32m[*] Running Certbot for: {new_domain}\033[0m")
    print("    (Make sure DNS is already pointing to this server.)\n")

    certbot_result = subprocess.run(
        f"certbot --nginx -d {new_domain} --non-interactive --agree-tos "
        f"--register-unsafely-without-email --redirect",
        shell=True
    )

    if certbot_result.returncode == 0:
        print("\n\033[1;32m -> SSL issued successfully! Processing Database migration...\033[0m")

        # -------------------------------------------------------------------------
        # STEP 4: Strict Database Search & Replace using the True Old URL
        # -------------------------------------------------------------------------
        if wp_old_url:
            print(f"\n\033[1;34m[*] Performing precise Search & Replace in Database...\033[0m")
            print(f" -> Target: \033[1;31m{wp_old_url}\033[0m → \033[1;32m{new_url}\033[0m")
            subprocess.run(
                f"wp search-replace '{wp_old_url}' '{new_url}' --path={wp_path} --allow-root --precise --skip-columns=guid", 
                shell=True
            )
        
        # Double safety net: explicitly force core options update anyway
        print("\n -> Enforcing core WP URLs...")
        subprocess.run(f"wp option update siteurl '{new_url}' --path={wp_path} --allow-root", shell=True)
        subprocess.run(f"wp option update home '{new_url}' --path={wp_path} --allow-root", shell=True)

        # -------------------------------------------------------------------------
        # STEP 5: Flush Redis Object Cache
        # -------------------------------------------------------------------------
        print(" -> Flushing Redis Object Cache...")
        subprocess.run(f"wp cache flush --path={wp_path} --allow-root", shell=True)

        print(f"\n\033[1;32m{'=' * 60}")
        print(f" -> Domain changed, SSL issued, and Database updated successfully.")
        print(f" -> Site is now live at: {new_url}")
        print(f"{'=' * 60}\033[0m")
    else:
        print(f"\n\033[1;33m[WARNING]\033[0m Certbot failed to issue SSL (DNS might not be propagated).")
        print("  Nginx vhost has been updated to the new domain, but WP Database was NOT migrated.")
        print(f"  Please verify DNS and retry manually: certbot --nginx -d {new_domain}")

    print("\nPress Enter to return to the main menu...")
    input()

def backup_database():
    """Backs up the WordPress database using WP-CLI, compresses it with gzip, and applies a 30-day retention policy."""
    backup_dir = '/var/backups/wordpress'
    wp_path = '/var/www/html'

    os.system('clear')
    print("\033[1;36m" + "=" * 60)
    print("              WordPress Database Backup                      ")
    print("=" * 60 + "\033[0m")

    # Ensure the backup directory exists
    os.makedirs(backup_dir, exist_ok=True)

    # Check if WordPress is actually deployed here
    if not os.path.exists(os.path.join(wp_path, 'wp-config.php')):
        print("\033[1;31m[ERROR]\033[0m WordPress installation not found at /var/www/html")
        print("Please deploy WordPress first before taking backups.")
        print("\nPress Enter to return to the main menu...")
        input()
        return

    print("\033[1;34m[*] Fetching site URL for descriptive backup naming...\033[0m")
    res_home = subprocess.run(
        f"wp option get home --path={wp_path} --allow-root", 
        shell=True, capture_output=True, text=True
    )
    
    # Extract domain name safely to use in the filename
    domain = "site"
    if res_home.returncode == 0 and res_home.stdout.strip():
        url = res_home.stdout.strip()
        domain = re.sub(r'https?://(www\.)?', '', url).replace('/', '_').strip()

    # Generate filename with timestamp (YYYYMMDD_HHMMSS)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    sql_filename = f"wp_db_{domain}_{timestamp}.sql"
    sql_path = os.path.join(backup_dir, sql_filename)
    gz_path = f"{sql_path}.gz"

    print(f"\n\033[1;32m[*] Exporting database via WP-CLI...\033[0m")
    print(f" -> Temporary file: {sql_path}")
    
    # Exporting DB without requiring any passwords
    export_cmd = subprocess.run(
        f"wp db export {sql_path} --path={wp_path} --allow-root",
        shell=True, capture_output=True, text=True
    )

    if export_cmd.returncode != 0:
        print("\033[1;31m[ERROR]\033[0m Failed to export database via WP-CLI.")
        print(export_cmd.stderr)
        print("\nPress Enter to return to the main menu...")
        input()
        return

    print("\033[1;32m -> Database exported successfully.\033[0m")
    print("\033[1;34m[*] Compressing backup file with gzip (Auto-removes raw .sql)...\033[0m")

    # gzip automatically compresses and deletes the source .sql file
    compress_cmd = subprocess.run(f"gzip -f {sql_path}", shell=True)

    if compress_cmd.returncode == 0:
        print(f"\033[1;32m -> Compression complete. Raw .sql file cleared.\033[0m")
        print(f" -> Backup successfully stored at: \033[1;36m{gz_path}\033[0m")

        # Smart Feature: Delete backups older than 30 days to prevent full disk crashes
        print("\n\033[1;34m[*] Running retention check (cleaning backups older than 30 days)...\033[0m")
        subprocess.run(f"find {backup_dir} -name 'wp_db_*.sql.gz' -mtime +30 -delete", shell=True)
        print("\033[1;32m -> Retention policy applied cleanly.\033[0m")

        print(f"\n\033[1;32m{'=' * 60}")
        print(" Database backup process completed successfully!")
        print(f"{'=' * 60}\033[0m")
    else:
        print("\033[1;31m[ERROR]\033[0m Failed to compress the backup file.")

    print("\nPress Enter to return to the main menu...")
    input()

# =============================================================================
# [6] SERVER MONITOR — bilingual Discord webhook alerting
# =============================================================================

_PULSE_STRINGS = {
    "en": {
        # Setup UI
        "header":            "Server Monitor — Discord Webhook Setup",
        "label_profile":     "Profile",
        "label_cron":        "Cron interval (auto-selected)",
        "label_monitors":    "Monitors",
        "found_existing":    "Existing config found",
        "keep_or_override":  "Press Enter to keep it, or paste a new URL to override.",
        "prompt_webhook_new":"Discord Webhook URL (required): ",
        "prompt_webhook_old":"Discord Webhook URL [Enter = keep current]: ",
        "err_webhook":       "Invalid URL. Expected: https://discord.com/api/webhooks/<id>/<token>",
        "testing_webhook":   "Testing webhook connection...",
        "err_test_failed":   "Could not reach the webhook. Check the URL and Discord channel permissions.",
        "webhook_ok":        "Webhook is live! Test message delivered successfully.",
        "summary_header":    "Server Monitor installed successfully!",
        "summary_config":    "Config",
        "summary_script":    "Pulse script",
        "summary_cron":      "Cron file",
        "summary_schedule":  "Schedule",
        "tip_uninstall":     "To uninstall the monitor, delete:",
        "press_enter":       "\nPress Enter to return to the main menu...",
        # Discord embed — install test
        "test_title":        "✅ InitOps — Connection successful",
        "test_desc": (
            "Server Monitor has been installed successfully!\n\n"
            "**Profile:** `{profile}`\n"
            "**Cron interval:** `{cron}`\n"
            "**Alert thresholds:** Disk >{disk}% | RAM >{ram}% | CPU >{cpu}%"
        ),
        # Discord embed — disk
        "disk_alert_title":    "🔴 Alert: Disk space critical!",
        "disk_alert_desc":     "**Server:** `{host}`\n{info}\nThreshold: **{threshold}%**",
        "disk_alert_info_row": "**{mount}**: {pct}% used",
        "disk_recv_title":     "🟢 Recovered: Disk space is healthy",
        "disk_recv_desc":      "**Server:** `{host}`\nDisk usage has returned to safe levels.",
        # Discord embed — RAM
        "ram_alert_title":     "🔴 Alert: RAM almost exhausted!",
        "ram_alert_desc":      "**Server:** `{host}`\nRAM in use: **{used}MB / {total}MB** ({pct}%)\nThreshold: **{threshold}%**",
        "ram_recv_title":      "🟢 Recovered: RAM is healthy",
        "ram_recv_desc":       "**Server:** `{host}`\nCurrent RAM: **{used}MB / {total}MB** ({pct}%)",
        # Discord embed — CPU
        "cpu_alert_title":     "🔴 Alert: CPU overloaded!",
        "cpu_alert_desc":      "**Server:** `{host}`\nLoad Average (1m): **{load}** / {cores} cores\nThreshold: **{threshold}%** per core",
        "cpu_recv_title":      "🟢 Recovered: CPU load is normal",
        "cpu_recv_desc":       "**Server:** `{host}`\nLoad Average (1m): **{load}** — back to safe range.",
        # Discord embed — MySQL
        "mysql_alert_title":   "🔴 Alert: MySQL is not responding!",
        "mysql_alert_desc":    "**Server:** `{host}`\n`mysqladmin ping` failed.\nPlease check the MariaDB service immediately.",
        "mysql_recv_title":    "🟢 Recovered: MySQL is back online",
        "mysql_recv_desc":     "**Server:** `{host}`\nMariaDB is responding normally.",
        # Embed footer
        "embed_footer":        "InitOps v{version} • Server Monitor",
    },
    "vi": {
        # Setup UI
        "header":            "Server Monitor — Cấu hình Discord Webhook",
        "label_profile":     "Profile",
        "label_cron":        "Cron interval (tự động chọn)",
        "label_monitors":    "Theo dõi",
        "found_existing":    "Đã tìm thấy cấu hình cũ",
        "keep_or_override":  "Nhấn Enter để giữ nguyên, hoặc nhập URL mới để ghi đè.",
        "prompt_webhook_new":"Discord Webhook URL (bắt buộc): ",
        "prompt_webhook_old":"Discord Webhook URL [Enter = giữ nguyên]: ",
        "err_webhook":       "URL không hợp lệ. Định dạng đúng: https://discord.com/api/webhooks/<id>/<token>",
        "testing_webhook":   "Đang kiểm tra kết nối webhook...",
        "err_test_failed":   "Không gửi được tin nhắn test. Kiểm tra lại URL hoặc quyền webhook trong Discord.",
        "webhook_ok":        "Webhook hoạt động! Tin nhắn test đã được gửi thành công.",
        "summary_header":    "Server Monitor đã cài đặt thành công!",
        "summary_config":    "Config",
        "summary_script":    "Pulse script",
        "summary_cron":      "Cron file",
        "summary_schedule":  "Schedule",
        "tip_uninstall":     "Để gỡ cài đặt monitor, xóa file:",
        "press_enter":       "\nNhấn Enter để quay lại menu chính...",
        # Discord embed — install test
        "test_title":        "✅ InitOps — Kết nối thành công",
        "test_desc": (
            "Server Monitor đã được cài đặt thành công!\n\n"
            "**Profile:** `{profile}`\n"
            "**Cron interval:** `{cron}`\n"
            "**Ngưỡng cảnh báo:** Disk >{disk}% | RAM >{ram}% | CPU >{cpu}%"
        ),
        # Discord embed — disk
        "disk_alert_title":    "🔴 Cảnh báo: Ổ đĩa gần đầy!",
        "disk_alert_desc":     "**Server:** `{host}`\n{info}\nNgưỡng: **{threshold}%**",
        "disk_alert_info_row": "**{mount}**: {pct}% đã dùng",
        "disk_recv_title":     "🟢 Phục hồi: Ổ đĩa đã ổn định",
        "disk_recv_desc":      "**Server:** `{host}`\nDung lượng ổ đĩa đã trở về mức an toàn.",
        # Discord embed — RAM
        "ram_alert_title":     "🔴 Cảnh báo: RAM sắp cạn!",
        "ram_alert_desc":      "**Server:** `{host}`\nRAM đang dùng: **{used}MB / {total}MB** ({pct}%)\nNgưỡng: **{threshold}%**",
        "ram_recv_title":      "🟢 Phục hồi: RAM đã ổn định",
        "ram_recv_desc":       "**Server:** `{host}`\nRAM hiện tại: **{used}MB / {total}MB** ({pct}%)",
        # Discord embed — CPU
        "cpu_alert_title":     "🔴 Cảnh báo: CPU quá tải!",
        "cpu_alert_desc":      "**Server:** `{host}`\nLoad Average (1m): **{load}** / {cores} cores\nNgưỡng: **{threshold}%** mỗi core",
        "cpu_recv_title":      "🟢 Phục hồi: CPU đã ổn định",
        "cpu_recv_desc":       "**Server:** `{host}`\nLoad Average (1m): **{load}** — đã về mức bình thường.",
        # Discord embed — MySQL
        "mysql_alert_title":   "🔴 Cảnh báo: MySQL không phản hồi!",
        "mysql_alert_desc":    "**Server:** `{host}`\n`mysqladmin ping` thất bại.\nVui lòng kiểm tra dịch vụ MariaDB ngay lập tức.",
        "mysql_recv_title":    "🟢 Phục hồi: MySQL đã hoạt động trở lại",
        "mysql_recv_desc":     "**Server:** `{host}`\nMariaDB đã phản hồi bình thường.",
        # Embed footer
        "embed_footer":        "InitOps v{version} • Server Monitor",
    },
}

def _pulse_t(lang, key, **kwargs):
    """Translate + interpolate. Falls back to 'en' when key missing."""
    table = _PULSE_STRINGS.get(lang, _PULSE_STRINGS["en"])
    text  = table.get(key) or _PULSE_STRINGS["en"].get(key, key)
    return text.format(**kwargs) if kwargs else text

def _send_discord_webhook(webhook_url, title, description,
                          footer="InitOps • Server Monitor", color=0xED4245):
    """POST a Discord Rich Embed. Returns True on HTTP 200/204, False otherwise.
    Uses stdlib only — no third-party dependencies required."""
    payload = {
        "embeds": [{
            "title":       title,
            "description": description,
            "color":       color,
            "footer":      {"text": footer},
            "timestamp":   datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z"),
        }]
    }
    data = json.dumps(payload).encode("utf-8")
    req  = urllib.request.Request(
        webhook_url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "User-Agent":   f"InitOps/{VERSION}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status in (200, 204)
    except Exception:
        return False

def _write_pulse_script(script_path, config_path):
    """Generate /usr/local/bin/init-server-pulse.sh.
    The script is fully self-contained:
    - Sources PULSE_CONFIG_FILE for webhook URL, lang, thresholds, cpu count
    - Bilingual string table embedded at generation time (no Python at cron runtime)
    - t() bash helper resolves STR_<lang>_<key> with English fallback
    - Anti-spam: one .lock file per metric; fires once on alert, once on recovery
    - JSON payload encoded via python3 to handle special characters safely
    - Native Linux commands only; total runtime < 0.1 s
    """
    # Flatten Python string table → bash variable assignments
    str_var_lines = []
    for lang_code, tbl in _PULSE_STRINGS.items():
        for key, val in tbl.items():
            safe = val.replace("\\", "\\\\").replace('"', '\\"').replace("`", "\\`")
            str_var_lines.append(f'STR_{lang_code}_{key}="{safe}"')
    bash_string_block = "\n".join(str_var_lines)

    script = r"""#!/bin/bash
# =============================================================================
# init-server-pulse.sh — InitOps Server Monitor
# Auto-generated by InitOps v__VERSION__. Do not edit manually.
# Re-run option [6] from the InitOps menu to reconfigure.
# =============================================================================

CONFIG_FILE="__CONFIG_PATH__"
[ ! -f "$CONFIG_FILE" ] && exit 0

# shellcheck source=/dev/null
source "$CONFIG_FILE"

# Only en/vi accepted; fall back to en
[[ "$LANG" != "vi" && "$LANG" != "en" ]] && LANG="en"

LOCK_DIR="/tmp/initops_pulse"
mkdir -p "$LOCK_DIR"

# =============================================================================
# Embedded bilingual string table (generated at install time)
# =============================================================================
__STRING_TABLE__

# =============================================================================
# t() — translate and interpolate {placeholder} tokens
# Usage: t KEY [placeholder=value ...]
# =============================================================================
t() {
    local KEY="$1"; shift
    local VAR="STR_${LANG}_${KEY}"
    local TEXT="${!VAR}"
    if [ -z "$TEXT" ]; then
        VAR="STR_en_${KEY}"
        TEXT="${!VAR}"
    fi
    for PAIR in "$@"; do
        local PH="${PAIR%%=*}"
        local VAL="${PAIR#*=}"
        TEXT="${TEXT//\{${PH}\}/${VAL}}"
    done
    printf '%s' "$TEXT"
}

# =============================================================================
# json_str() — safely JSON-encode a string via python3
# =============================================================================
json_str() {
    printf '%s' "$1" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()), end="")'
}

# =============================================================================
# send_discord() — POST a Rich Embed to the configured webhook
# $1=title  $2=description  $3=color_decimal (optional)
# =============================================================================
send_discord() {
    local TITLE="$1"
    local DESC="$2"
    local COLOR="${3:-15418949}"
    local TS FOOTER
    TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    FOOTER=$(t embed_footer "version=${VERSION:-1.4.0}")

    curl -s -o /dev/null \
        -H "Content-Type: application/json" \
        -X POST \
        -d "{
  \"embeds\": [{
    \"title\":       $(json_str "$TITLE"),
    \"description\": $(json_str "$DESC"),
    \"color\":       ${COLOR},
    \"footer\":      {\"text\": $(json_str "$FOOTER")},
    \"timestamp\":   \"${TS}\"
  }]
}" \
        "$WEBHOOK_URL" 2>/dev/null
}

# =============================================================================
# handle_alert() — fire-once alert + fire-once recovery via lock files
# $1=metric_key  $2=alert_title  $3=alert_desc
# $4=recv_title  $5=recv_desc    $6=is_alert (1|0)
# =============================================================================
handle_alert() {
    local KEY="$1" ALERT_TITLE="$2" ALERT_DESC="$3"
    local RECV_TITLE="$4" RECV_DESC="$5" IS_ALERT="$6"
    local LOCK_FILE="$LOCK_DIR/pulse_${KEY}.lock"

    if [ "$IS_ALERT" -eq 1 ]; then
        if [ ! -f "$LOCK_FILE" ]; then
            send_discord "$ALERT_TITLE" "$ALERT_DESC" "15418949"
            touch "$LOCK_FILE"
        fi
    else
        if [ -f "$LOCK_FILE" ]; then
            send_discord "$RECV_TITLE" "$RECV_DESC" "5763719"
            rm -f "$LOCK_FILE"
        fi
    fi
}

HOSTNAME_VAL=$(hostname -f 2>/dev/null || hostname)

# =============================================================================
# METRIC 1: DISK — all real mount points vs DISK_THRESHOLD
# =============================================================================
DISK_ALERT=0
DISK_INFO=""

while IFS= read -r LINE; do
    PCT=$(echo "$LINE" | awk '{print $5}' | tr -d '%')
    MNT=$(echo "$LINE" | awk '{print $6}')
    if [ -n "$PCT" ] && [ "$PCT" -ge "$DISK_THRESHOLD" ] 2>/dev/null; then
        DISK_ALERT=1
        ROW=$(t disk_alert_info_row "mount=${MNT}" "pct=${PCT}")
        DISK_INFO="${DISK_INFO}${ROW}\n"
    fi
done < <(df -h --output=source,size,used,avail,pcent,target 2>/dev/null \
         | tail -n +2 \
         | grep -Ev '^(tmpfs|udev|none|overlay|shm)')

if [ "$DISK_ALERT" -eq 1 ]; then
    handle_alert "disk" \
        "$(t disk_alert_title)" \
        "$(t disk_alert_desc "host=${HOSTNAME_VAL}" "info=${DISK_INFO}" "threshold=${DISK_THRESHOLD}")" \
        "$(t disk_recv_title)" \
        "$(t disk_recv_desc  "host=${HOSTNAME_VAL}")" \
        1
else
    handle_alert "disk" "" "" \
        "$(t disk_recv_title)" \
        "$(t disk_recv_desc "host=${HOSTNAME_VAL}")" \
        0
fi

# =============================================================================
# METRIC 2: RAM — free -m vs RAM_THRESHOLD
# =============================================================================
RAM_TOTAL=$(free -m 2>/dev/null | awk '/^Mem:/{print $2}')
RAM_USED=$( free -m 2>/dev/null | awk '/^Mem:/{print $3}')
RAM_PCT=0
if [ -n "$RAM_TOTAL" ] && [ "$RAM_TOTAL" -gt 0 ] 2>/dev/null; then
    RAM_PCT=$(( RAM_USED * 100 / RAM_TOTAL ))
fi

RAM_ALERT=0
[ "$RAM_PCT" -ge "$RAM_THRESHOLD" ] 2>/dev/null && RAM_ALERT=1

handle_alert "ram" \
    "$(t ram_alert_title)" \
    "$(t ram_alert_desc "host=${HOSTNAME_VAL}" "used=${RAM_USED}" "total=${RAM_TOTAL}" "pct=${RAM_PCT}" "threshold=${RAM_THRESHOLD}")" \
    "$(t ram_recv_title)" \
    "$(t ram_recv_desc  "host=${HOSTNAME_VAL}" "used=${RAM_USED}" "total=${RAM_TOTAL}" "pct=${RAM_PCT}")" \
    "$RAM_ALERT"

# =============================================================================
# METRIC 3: CPU load avg (1m) — integer × 100, limit = CPU_CORES × CPU_THRESHOLD
# e.g. 4 cores × 90 = 360 → triggers at load avg ≥ 3.60
# =============================================================================
LOAD_RAW=$(uptime 2>/dev/null \
    | awk -F'load average[s]*:' '{print $2}' \
    | awk -F',' '{print $1}' \
    | tr -d ' ')
LOAD_INT=$(echo "$LOAD_RAW" | sed 's/\.//' | sed 's/^0*//')
[ -z "$LOAD_INT" ] && LOAD_INT=0
CPU_LIMIT=$(( CPU_CORES * CPU_THRESHOLD ))

CPU_ALERT=0
[ "$LOAD_INT" -ge "$CPU_LIMIT" ] 2>/dev/null && CPU_ALERT=1

handle_alert "cpu" \
    "$(t cpu_alert_title)" \
    "$(t cpu_alert_desc "host=${HOSTNAME_VAL}" "load=${LOAD_RAW}" "cores=${CPU_CORES}" "threshold=${CPU_THRESHOLD}")" \
    "$(t cpu_recv_title)" \
    "$(t cpu_recv_desc  "host=${HOSTNAME_VAL}" "load=${LOAD_RAW}")" \
    "$CPU_ALERT"

# =============================================================================
# METRIC 4: MySQL / MariaDB — mysqladmin ping (Unix socket, no credentials)
# =============================================================================
MYSQL_ALERT=0
mysqladmin ping --silent 2>/dev/null || MYSQL_ALERT=1

handle_alert "mysql" \
    "$(t mysql_alert_title)" \
    "$(t mysql_alert_desc "host=${HOSTNAME_VAL}")" \
    "$(t mysql_recv_title)" \
    "$(t mysql_recv_desc  "host=${HOSTNAME_VAL}")" \
    "$MYSQL_ALERT"
"""

    script = script.replace("__VERSION__",      VERSION)
    script = script.replace("__CONFIG_PATH__",  config_path)
    script = script.replace("__STRING_TABLE__", bash_string_block)

    with open(script_path, 'w') as f:
        f.write(script)

def setup_server_monitor():
    """Interactive setup wizard for Server Monitor (option [6]).
    1. Language selection (en / vi)
    2. Discord Webhook URL input & live connectivity test
    3. Persist config to PULSE_CONFIG_FILE (chmod 600)
    4. Generate PULSE_SCRIPT_PATH bash monitor script
    5. Install PULSE_CRON_D_PATH cron job (root, profile-aware interval)
    Fully self-contained — zero side effects on existing flows.
    """
    cpu_cores, ram_mb, profile, profile_txt = get_system_resources()

    # Larger servers poll less frequently — they have more headroom and
    # their metrics change more slowly than a micro VPS under load.
    CRON_MAP = {
        "micro":    "*/5 * * * *",
        "small":    "*/5 * * * *",
        "standard": "*/10 * * * *",
        "medium":   "*/15 * * * *",
        "large":    "*/20 * * * *",
        "xlarge":   "*/30 * * * *",
    }
    cron_schedule = CRON_MAP.get(profile, "*/10 * * * *")

    # -------------------------------------------------------------------------
    # Language selection
    # -------------------------------------------------------------------------
    os.system('clear')
    print("\033[1;36m" + "=" * 60)
    print("            Server Monitor — Language / Ngôn ngữ              ")
    print("=" * 60 + "\033[0m")
    print(" [1] English  (default)")
    print(" [2] Tiếng Việt")
    print("-" * 60)
    while True:
        lc = input("Select / Chọn (1/2) [Enter = 1]: ").strip()
        if lc in ("", "1"):
            lang = "en"; break
        if lc == "2":
            lang = "vi"; break
        print(" Please enter 1 or 2.")

    def t(key, **kw):
        return _pulse_t(lang, key, **kw)

    # -------------------------------------------------------------------------
    # Header
    # -------------------------------------------------------------------------
    os.system('clear')
    print("\033[1;36m" + "=" * 60)
    print(f"  {t('header')}")
    print("=" * 60 + "\033[0m")
    print(f" [{t('label_profile')}]:   \033[1;33m{profile_txt}\033[0m")
    print(f" [{t('label_cron')}]:   \033[1;32m{cron_schedule}\033[0m")
    print(f" [{t('label_monitors')}]:   Disk >{PULSE_DISK_THRESHOLD}%  |  RAM >{PULSE_RAM_THRESHOLD}%  |  CPU >{PULSE_CPU_THRESHOLD}%  |  MySQL")
    print("-" * 60)

    # -------------------------------------------------------------------------
    # Load existing webhook from config (if any)
    # -------------------------------------------------------------------------
    existing_webhook = ""
    if os.path.exists(PULSE_CONFIG_FILE):
        try:
            with open(PULSE_CONFIG_FILE, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("WEBHOOK_URL="):
                        existing_webhook = line.split("=", 1)[1].strip('"')
        except Exception:
            pass

    if existing_webhook:
        masked = existing_webhook[:46] + "..." if len(existing_webhook) > 46 else existing_webhook
        print(f" [!] {t('found_existing')}: \033[1;33m{masked}\033[0m")
        print(f"     {t('keep_or_override')}\n")

    # -------------------------------------------------------------------------
    # Webhook URL — input & format validation
    # -------------------------------------------------------------------------
    webhook_re = re.compile(r'^https://discord(?:app)?\.com/api/webhooks/\d+/[\w-]+$')
    while True:
        if existing_webhook:
            raw = input(t("prompt_webhook_old")).strip()
            if not raw:
                webhook_url = existing_webhook
                break
        else:
            raw = input(t("prompt_webhook_new")).strip()
        if webhook_re.match(raw):
            webhook_url = raw
            break
        print(f"\033[1;31m[Error]\033[0m {t('err_webhook')}")

    # -------------------------------------------------------------------------
    # Live webhook test — abort before writing anything if unreachable
    # -------------------------------------------------------------------------
    print(f"\n\033[1;34m[*] {t('testing_webhook')}\033[0m")
    test_ok = _send_discord_webhook(
        webhook_url,
        title=t("test_title"),
        description=t(
            "test_desc",
            profile=profile_txt,
            cron=cron_schedule,
            disk=PULSE_DISK_THRESHOLD,
            ram=PULSE_RAM_THRESHOLD,
            cpu=PULSE_CPU_THRESHOLD,
        ),
        footer=t("embed_footer", version=VERSION),
        color=0x57F287,
    )
    if not test_ok:
        print(f"\033[1;31m[ERROR]\033[0m {t('err_test_failed')}")
        print(t("press_enter"))
        input()
        return
    print(f"\033[1;32m -> {t('webhook_ok')}\033[0m")

    # -------------------------------------------------------------------------
    # Persist config (root-only readable)
    # -------------------------------------------------------------------------
    config_lines = (
        f'WEBHOOK_URL="{webhook_url}"\n'
        f'LANG="{lang}"\n'
        f'PROFILE="{profile}"\n'
        f'DISK_THRESHOLD="{PULSE_DISK_THRESHOLD}"\n'
        f'RAM_THRESHOLD="{PULSE_RAM_THRESHOLD}"\n'
        f'CPU_THRESHOLD="{PULSE_CPU_THRESHOLD}"\n'
        f'CPU_CORES="{cpu_cores}"\n'
        f'VERSION="{VERSION}"\n'
    )
    with open(PULSE_CONFIG_FILE, 'w') as f:
        f.write(config_lines)
    os.chmod(PULSE_CONFIG_FILE, 0o600)

    # -------------------------------------------------------------------------
    # Generate bash pulse script
    # -------------------------------------------------------------------------
    _write_pulse_script(PULSE_SCRIPT_PATH, PULSE_CONFIG_FILE)
    os.chmod(PULSE_SCRIPT_PATH, 0o755)

    # -------------------------------------------------------------------------
    # Install /etc/cron.d job — runs as root (needed for mysqladmin)
    # -------------------------------------------------------------------------
    cron_body = (
        "# initops-server-pulse — managed by InitOps. Do not edit manually.\n"
        "SHELL=/bin/bash\n"
        "PATH=/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin\n"
        f"{cron_schedule} root /bin/bash {PULSE_SCRIPT_PATH} > /dev/null 2>&1\n"
    )
    with open(PULSE_CRON_D_PATH, 'w') as f:
        f.write(cron_body)
    os.chmod(PULSE_CRON_D_PATH, 0o644)

    # -------------------------------------------------------------------------
    # Summary
    # -------------------------------------------------------------------------
    print(f"\n\033[1;32m{'=' * 60}")
    print(f"  {t('summary_header')}")
    print(f"{'=' * 60}\033[0m")
    print(f" -> {t('summary_config')}:        {PULSE_CONFIG_FILE}")
    print(f" -> {t('summary_script')}:  {PULSE_SCRIPT_PATH}")
    print(f" -> {t('summary_cron')}:       {PULSE_CRON_D_PATH}")
    print(f" -> {t('summary_schedule')}:     \033[1;33m{cron_schedule}\033[0m  ({profile})")
    print(f"\n \033[1;36m[TIP] {t('tip_uninstall')} {PULSE_CRON_D_PATH}\033[0m")
    print(t("press_enter"))
    input()

def main():
    check_os()
    sys.stdin = open('/dev/tty', 'r')
    while True:
        cpu, ram, profile, profile_txt = get_system_resources()
        is_deployed = os.path.exists(LOCK_FILE)

        os.system('clear')
        print("\033[1;36m" + "=" * 60)
        print(f"                    InitOps v{VERSION}                          ")
        print("=" * 60 + "\033[0m")
        print(f" [System]:              {cpu} CPU Cores | {ram} MB RAM")
        print(f" [Optimization Profile]: \033[1;33m{profile_txt}\033[0m")
        print("-" * 60)

        if not is_deployed:
            print(" [1] Deploy LEMP Stack & WordPress")
        else:
            print(" \033[1;30m[1] Deploy LEMP Stack & WordPress (ALREADY INSTALLED)\033[0m")

        print(" [2] Re-apply Performance Optimizations (Use after server upgrade)")
        print(" [3] Help & Tuning Paths")

        if is_deployed:
            print(" [4] Change Domain & Renew SSL")
        else:
            print(" \033[1;30m[4] Change Domain & Renew SSL (Deploy first)\033[0m")

        print(" [5] Backup WordPress Database")
        print(" [6] Server Monitor (Discord Webhook)")
        print(" [0] Exit")
        print("-" * 60)

        choice = input("Option (0-6): ").strip()

        if choice == "1":
            if is_deployed:
                print("\n\033[1;31m[ERROR]\033[0m Environment is already deployed.")
                print("To prevent data loss, re-installation is blocked.")
                print("Press Enter to continue...")
                input()
                continue

            print("\n\033[1;34m--- Deployment Configuration ---\033[0m")
            domain    = validate_domain("-> Domain name (e.g. site.com) [Default: _]: ")
            db_name   = validate_input("-> Database name   [Default: wp_production]: ", "wp_production")
            db_user   = f"wp_user_{secrets.randbelow(8999) + 1000}"
            db_prefix = validate_input("-> Table prefix    [Default: wp_]:           ", "wp_", r'^[a-zA-Z0-9_]+$')

            install_packages()
            setup_firewall()
            setup_fail2ban()
            apply_tuning(profile, ram, cpu)
            db_pass = deploy_wordpress(domain, db_name, db_user, db_prefix)
            setup_system_cron()

            with open(LOCK_FILE, 'w') as f:
                f.write("deployed")

            print("\n\033[1;32m" + "=" * 60)
            print("              Deployment completed successfully               ")
            print("=" * 60 + "\033[0m")
            print(f" -> Version:           {VERSION}")
            print(f" -> Web root:          /var/www/html")
            print(f" -> Domain:            {domain if domain != '_' else 'Direct Public IP'}")
            print(f" -> Database:          {db_name}")
            print(f" -> Database user:     {db_user}")
            print(f" -> Database password: {db_pass}")
            print(f" -> Table prefix:      {db_prefix}")
            print(f" -> Socket mode:       Enabled (MySQL + Redis)")
            print("=" * 60)
            print("\033[1;33m[!] Save these credentials securely. They will not be shown again.\033[0m")
            if domain != "_":
                print(f"\n\033[1;36m[TIP] To enable HTTPS, ensure your domain points here and run:\033[0m")
                print(f"      certbot --nginx -d {domain}")
            else:
                print("\n\033[1;36m[TIP] To enable HTTPS later, point a domain here and run 'certbot --nginx'\033[0m")
            print("\nOpen your domain/IP in a browser to complete the WordPress setup.\n")
            break

        elif choice == "2":
            if not is_deployed:
                print("\n\033[1;33m[WARNING]\033[0m Base stack not deployed yet. Please run Option 1 first.")
                print("Press Enter to continue...")
                input()
                continue

            print("\n\033[1;34m--- Re-applying Optimizations ---\033[0m")
            print("Detecting latest hardware specs...")
            apply_tuning(profile, ram, cpu)
            print("\nPress Enter to return to the main menu...")
            input()

        elif choice == "3":
            print_help_menu()

        elif choice == "4":
            if not is_deployed:
                print("\n\033[1;33m[WARNING]\033[0m Base stack not deployed yet. Please run Option 1 first.")
                print("Press Enter to continue...")
                input()
                continue

            change_domain()

        elif choice == "5":
            if not is_deployed:
                print("\n\\033[1;33m[WARNING]\\033[0m Base stack not deployed yet. Please run Option 1 first.")
                print("Press Enter to continue...")
                input()
                continue
            
            backup_database()

        elif choice == "6":
            setup_server_monitor()

        elif choice == "0":
            print("Exiting.")
            sys.exit(0)

        else:
            print("Invalid selection. Press Enter to try again...")
            input()

if __name__ == "__main__":
    main()