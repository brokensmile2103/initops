# InitOps v1.6.0

> **One-command LEMP stack + WordPress deployment engine for Ubuntu 24.04 LTS.**
>
> Optimized for real-world VPS tiers — from 1 GB micro instances to 32 GB+ dedicated servers.

[![Ubuntu](https://img.shields.io/badge/Ubuntu-24.04%20LTS-E95420?logo=ubuntu&logoColor=white)](https://ubuntu.com/)
[![Nginx](https://img.shields.io/badge/Nginx-1.24+-009639?logo=nginx&logoColor=white)](https://nginx.org/)
[![PHP](https://img.shields.io/badge/PHP-8.3-777BB4?logo=php&logoColor=white)](https://www.php.net/)
[![MariaDB](https://img.shields.io/badge/MariaDB-10.11+-003545?logo=mariadb&logoColor=white)](https://mariadb.org/)
[![Redis](https://img.shields.io/badge/Redis-7.0+-DC382D?logo=redis&logoColor=white)](https://redis.io/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

## What is InitOps?

**InitOps** is a single-file, interactive Python CLI that turns a fresh Ubuntu 24.04 server into a production-ready WordPress host in minutes.

No Docker. No Ansible. No 500-line bash scripts. Just run one command, answer a few prompts, and get:

- **LEMP Stack** — Nginx, MariaDB, PHP 8.3-FPM, Redis
- **Security Hardening** — iptables firewall, Fail2Ban, socket-only DB/Redis
- **Auto-Tuned Performance** — 6 hardware profiles (micro → xlarge)
- **Multi-Site Support** — Deploy multiple WordPress sites on the same VPS
- **Discord Monitoring** — Bilingual server health alerts (EN/VI)
- **Domain Migration** — One-shot domain change + SSL + DB search-replace
- **Smart Backups** — WP-CLI exports with gzip + 30-day retention (single or all sites)
- **DNS-01 SSL Auto-Renewal** — Cloudflare DNS challenge for seamless cert renewal

## Quick Start

```bash
# Run as root on a fresh Ubuntu 24.04 LTS server
curl -fsSL https://raw.githubusercontent.com/brokensmile2103/initops/main/install.sh | bash
```

Or:

```bash
curl -fsSL https://inithtml.com/initops/install.sh | bash
```

After installation, relaunch anytime with:

```bash
initops
```

## Requirements

| Requirement | Details |
|-------------|---------|
| **OS** | Ubuntu 24.04 LTS (Noble Numbat) |
| **Privileges** | Root (`sudo` or `root` user) |
| **Network** | Internet access for package installation |
| **RAM** | 1 GB minimum (2 GB+ recommended) |

## Features

### 1. Smart Hardware Profiling
Automatically detects your server's RAM and CPU, then applies the optimal configuration:

| Profile | RAM Range | Use Case |
|---------|-----------|----------|
| `micro` | < 1.5 GB | Entry-level VPS |
| `small` | 1.5 – 3.5 GB | Budget VPS |
| `standard` | 3.5 – 6 GB | **4 GB VPS (recommended)** |
| `medium` | 6 – 14 GB | 8–12 GB VPS |
| `large` | 14 – 24 GB | 16 GB VPS |
| `xlarge` | 24 GB+ | Dedicated servers |

Each profile tunes:
- Nginx worker connections & buffer sizes
- PHP-FPM `pm.max_children` & memory limits
- MariaDB `innodb_buffer_pool_size` (up to 45% of RAM)
- Redis `maxmemory` & eviction policies

### 2. Kernel & TCP Stack Tuning

InitOps automatically applies a comprehensive kernel tuning set to maximize network throughput, stabilize connections, and accelerate response times:

- **TCP BBR** — Enables the BBR congestion control algorithm instead of Cubic, significantly reducing latency and improving page load speed.
- **File Limits** — Raises `fs.file-max` to 2,000,000 and `fs.inotify.max_user_watches` to 524,288, ensuring Nginx + PHP-FPM are not descriptor-bound under high traffic.
- **Connection Backlog** — Pushes `net.core.somaxconn`, `tcp_max_syn_backlog`, and `netdev_max_backlog` to 65,535, combined with `tcp_syncookies = 1` to mitigate SYN flood / light DDoS spikes.
- **Socket Lifecycle** — Enables `tcp_tw_reuse`, lowers `tcp_fin_timeout` to 15s, fine-tunes keepalive probes (600s / 30s / 5 attempts), and expands `ip_local_port_range` to 1024–65000 for efficient port reuse.
- **Redis Background Save** — Sets `vm.overcommit_memory = 1` to prevent OOM failures when Redis performs BGSAVE on memory-constrained VPS.

All configurations are written to `/etc/sysctl.d/99-initops-kernel.conf` and applied immediately via `sysctl --system` — no reboot required.

### 3. Intelligent Swap Management

InitOps does not create swap rigidly for every profile; instead, it **allocates dynamically based on actual RAM capacity**:

| Profile | RAM Range | Swap Allocation |
|---------|-----------|-----------------|
| `micro` | &lt; 1.5 GB | **2 GB swap file** |
| `small` | 1.5 – 3.5 GB | **2 GB swap file** |
| `standard` | 3.5 – 6 GB | **1 GB swap file** |
| `medium` and above | ≥ 6 GB | **None** — prioritizes keeping workload in physical RAM |

If the system already has an active swap (partition or file), InitOps **auto-detects and skips** to avoid conflicts. The swap file is persisted via `/etc/fstab` with `chmod 600` permissions.

Alongside swap, InitOps tunes two additional critical kernel parameters:

- `vm.swappiness = 10` — Forces the kernel to prioritize RAM usage, only swapping when RAM is critically low (&lt; 10%).
- `vm.vfs_cache_pressure = 50` — Keeps inode/dentry cache in RAM longer, accelerating Nginx and log rotation I/O.

### 4. Multi-Site on One VPS
Deploy multiple independent WordPress sites on the same server:

- Each site gets its own **database**, **Redis DB index**, and **Nginx vhost**
- Custom web root folder names (`/var/www/<your-folder>`)
- Isolated Redis databases (DB 0 for the first site, DB 1+ for additional sites)
- Per-site WP-Cron via `flock` to prevent overlapping processes
- Backup supports **all sites at once** or **individual selection**

### 5. Security by Default
- **iptables** — Ports 22, 80, 443 only
- **Fail2Ban** — SSH brute-force protection (5 retries / 1h ban)
- **Socket Mode** — MariaDB & Redis communicate via Unix sockets (no TCP exposure)
- **WP Hardening** — `DISALLOW_FILE_EDIT`, disabled XML-RPC, cron offloaded to system

### 6. Discord Server Monitor
Bilingual (English / Vietnamese) webhook alerting for:
- Disk space critical
- RAM exhaustion
- CPU overload
- MySQL/MariaDB downtime
- Auto-recovery notifications

Profile-aware cron intervals (every 5–10 minutes).

### 7. One-Shot Domain Migration
Change your domain without breaking anything:
- Updates Nginx vhost
- Issues new SSL via Certbot
- Performs precise DB search-replace (respects serialized data)
- Flushes Redis cache automatically

### 8. Database Backups
```
/var/backups/wordpress/wp_db_<domain>_<YYYYMMDD_HHMMSS>.sql.gz
```
- WP-CLI export (no password prompts)
- Auto-gzip compression
- Auto-cleanup: deletes backups older than 30 days
- **Multi-site aware** — backup all sites or select individual ones

### 9. DNS-01 SSL Auto-Renewal via Cloudflare
Migrate an existing cert to DNS challenge renewal — no re-issuance required, no port 80 dependency:

- Installs `python3-certbot-dns-cloudflare` plugin automatically
- Stores your API token in `/root/.secrets/cloudflare.ini` with `chmod 600`
- Patches the existing `/etc/letsencrypt/renewal/<domain>.conf` in-place (backup created first)
- Sets `dns_cloudflare_propagation_seconds = 60` for reliable TXT record propagation
- Creates a deploy hook to reload Nginx after each successful renewal
- Enables and verifies `certbot.timer` (runs twice daily)
- Runs a `--dry-run` test before finishing to confirm everything works

**Cloudflare API token permissions required:**

| Permission | Access |
|------------|--------|
| Zone → DNS | Edit |
| Zone → Zone | Read |

Set **Zone Resources** to *Include → Specific zone → your domain* — avoid "All zones" for least-privilege security.

## Interactive Menu

```
============================================================
                    InitOps v1.6.0
============================================================
 [System]:              4 CPU Cores | 4096 MB RAM
 [Optimization Profile]: Standard (3.5 – 6 GB | e.g. 4 GB VPS)
------------------------------------------------------------
 [1] Deploy LEMP Stack & WordPress
 [2] Re-apply Performance Optimizations (Use after server upgrade)
 [3] Help & Tuning Paths
 [4] Change Domain & Renew SSL
 [5] Backup WordPress Database
 [6] Server Monitor (Discord Webhook)
 [7] Add New Website
 [8] Configure DNS-01 SSL Auto-Renewal (Cloudflare)
 [0] Exit
------------------------------------------------------------
Option (0-8):
```

## Configuration Files

| Component | Path |
|-----------|------|
| Nginx Main | `/etc/nginx/nginx.conf` |
| Nginx Vhost (default) | `/etc/nginx/sites-available/wordpress` |
| PHP-FPM Pool | `/etc/php/8.3/fpm/pool.d/z_custom_pm.conf` |
| PHP Tuning | `/etc/php/8.3/fpm/conf.d/99-initops-runtime.ini` |
| MariaDB Tuning | `/etc/mysql/conf.d/z_custom_optimize.cnf` |
| Redis Config | `/etc/redis/redis.conf` |
| WP Config (default) | `/var/www/html/wp-config.php` |
| Sites Registry | `/etc/.initops_websites.conf` |
| Monitor Config | `/etc/.initops_pulse.conf` |
| Monitor Script | `/usr/local/bin/init-server-pulse.sh` |
| Cloudflare Credentials | `/root/.secrets/cloudflare.ini` |
| Certbot Deploy Hook | `/etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh` |

## Post-Deployment Checklist

1. **Point your domain** to the server's public IP
2. **Enable SSL:**
   ```bash
   certbot --nginx -d yourdomain.com
   ```
   *(Or use Option [4] in the InitOps menu for full migration)*
3. **Secure your credentials** — the DB password is shown once during deployment
4. **Install Redis Object Cache** and enable object caching in WordPress
5. *(Optional)* Install a page caching plugin such as **W3 Total Cache** if additional page caching, browser caching, or CDN integration is desired

## Adding More Sites

Use **Option [7]** in the InitOps menu to deploy additional WordPress sites:

```bash
initops
# Select [7] Add New Website
```

Each new site gets:
- Independent database with auto-generated credentials
- Dedicated Redis DB index (auto-incremented from DB 1)
- Custom web root folder under `/var/www/`
- Isolated Nginx vhost and System Cron

## License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.

> **Why MIT?** It's permissive, widely recognized, and lets anyone use InitOps for personal or commercial projects. The only requirement is keeping the copyright notice — which helps build trust and attribution.

## Support & Feedback

If you encounter any issues or have feature requests, please open an [Issue](https://github.com/brokensmile2103/initops/issues).

## Contributing

Pull requests are welcome! For major changes, please open an issue first to discuss what you would like to change.

## Disclaimer

**Use at your own risk.** InitOps modifies system-level configurations (nginx, mysql, redis, iptables, cron). Always back up your server or test on a non-production VM first. The authors are not responsible for data loss or service interruption.

## Acknowledgments

- [Ondřej Surý](https://deb.sury.org/) for the maintained PHP PPA
- [WordPress](https://wordpress.org/) & [WP-CLI](https://wp-cli.org/) teams
- The open-source Nginx, MariaDB, and Redis communities
