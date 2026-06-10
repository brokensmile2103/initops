
# InitOps v1.4.0

> **One-command LEMP stack + WordPress deployment engine for Ubuntu 24.04 LTS.**
> 
> Optimized for real-world VPS tiers — from 1 GB micro instances to 32 GB+ dedicated servers.

[![Ubuntu](https://img.shields.io/badge/Ubuntu-24.04%20LTS-E95420?logo=ubuntu&logoColor=white)](https://ubuntu.com/)
[![Nginx](https://img.shields.io/badge/Nginx-1.24+-009639?logo=nginx&logoColor=white)](https://nginx.org/)
[![PHP](https://img.shields.io/badge/PHP-8.3-777BB4?logo=php&logoColor=white)](https://www.php.net/)
[![MariaDB](https://img.shields.io/badge/MariaDB-10.11+-003545?logo=mariadb&logoColor=white)](https://mariadb.org/)
[![Redis](https://img.shields.io/badge/Redis-7.0+-DC382D?logo=redis&logoColor=white)](https://redis.io/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

## What is InitOps?

**InitOps** is a single-file, interactive Python CLI that turns a fresh Ubuntu 24.04 server into a production-ready WordPress host in minutes.

No Docker. No Ansible. No 500-line bash scripts. Just run one command, answer a few prompts, and get:

- **LEMP Stack** — Nginx, MariaDB, PHP 8.3-FPM, Redis
- **Security Hardening** — iptables firewall, Fail2Ban, socket-only DB/Redis
- **Auto-Tuned Performance** — 6 hardware profiles (micro → xlarge)
- **Discord Monitoring** — Bilingual server health alerts (EN/VI)
- **Domain Migration** — One-shot domain change + SSL + DB search-replace
- **Smart Backups** — WP-CLI exports with gzip + 30-day retention

---

## Quick Start

```bash
# Run as root on a fresh Ubuntu 24.04 LTS server
curl -fsSL https://inithtml.com/initops/install.sh | sudo bash
```

After installation, relaunch anytime with:

```bash
initops
```

---

## Requirements

| Requirement | Details |
|-------------|---------|
| **OS** | Ubuntu 24.04 LTS (Noble Numbat) |
| **Privileges** | Root (`sudo` or `root` user) |
| **Network** | Internet access for package installation |
| **RAM** | 1 GB minimum (2 GB+ recommended) |

---

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

### 2. Security by Default
- **iptables** — Ports 22, 80, 443 only
- **Fail2Ban** — SSH brute-force protection (5 retries / 1h ban)
- **Socket Mode** — MariaDB & Redis communicate via Unix sockets (no TCP exposure)
- **WP Hardening** — `DISALLOW_FILE_EDIT`, disabled XML-RPC, cron offloaded to system

### 3. Discord Server Monitor
Bilingual (English / Vietnamese) webhook alerting for:
- Disk space critical
- RAM exhaustion
- CPU overload
- MySQL/MariaDB downtime
- Auto-recovery notifications

Profile-aware cron intervals (every 5–30 minutes).

### 4. One-Shot Domain Migration
Change your domain without breaking anything:
- Updates Nginx vhost
- Issues new SSL via Certbot
- Performs precise DB search-replace (respects serialized data)
- Flushes Redis cache automatically

### 5. Database Backups
```
/var/backups/wordpress/wp_db_<domain>_<YYYYMMDD_HHMMSS>.sql.gz
```
- WP-CLI export (no password prompts)
- Auto-gzip compression
- Auto-cleanup: deletes backups older than 30 days

---

## Interactive Menu

```
============================================================
                    InitOps v1.4.0
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
 [0] Exit
------------------------------------------------------------
Option (0-6):
```

---

## Configuration Files

| Component | Path |
|-----------|------|
| Nginx Main | `/etc/nginx/nginx.conf` |
| Nginx Vhost | `/etc/nginx/sites-available/wordpress` |
| PHP-FPM Pool | `/etc/php/8.3/fpm/pool.d/z_custom_pm.conf` |
| PHP Tuning | `/etc/php/8.3/fpm/conf.d/99-initops-runtime.ini` |
| MariaDB Tuning | `/etc/mysql/conf.d/z_custom_optimize.cnf` |
| Redis Config | `/etc/redis/redis.conf` |
| WP Config | `/var/www/html/wp-config.php` |
| Monitor Config | `/etc/.initops_pulse.conf` |
| Monitor Script | `/usr/local/bin/init-server-pulse.sh` |

---

## Post-Deployment Checklist

1. **Point your domain** to the server's public IP
2. **Enable SSL:**
   ```bash
   certbot --nginx -d yourdomain.com
   ```
   *(Or use Option [4] in the InitOps menu for full migration)*
3. **Secure your credentials** — the DB password is shown once during deployment
4. **Install a caching plugin** (e.g., W3 Total Cache or LiteSpeed Cache) and point it to Redis

---

## License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.

> **Why MIT?** It's permissive, widely recognized, and lets anyone use InitOps for personal or commercial projects. The only requirement is keeping the copyright notice — which helps build trust and attribution.

---

## Support & Feedback

> If you encounter any issues or have feature requests, please open an [Issue](https://github.com/brokensmile2103/initops/issues).

---

## Contributing

> Pull requests are welcome! For major changes, please open an issue first to discuss what you would like to change.

---

## Disclaimer

> **Use at your own risk.** InitOps modifies system-level configurations (nginx, mysql, redis, iptables, cron). Always back up your server or test on a non-production VM first. The authors are not responsible for data loss or service interruption.

---

## Acknowledgments

- [Ondřej Surý](https://deb.sury.org/) for the maintained PHP PPA
- [WordPress](https://wordpress.org/) & [WP-CLI](https://wp-cli.org/) teams
- The open-source Nginx, MariaDB, and Redis communities
