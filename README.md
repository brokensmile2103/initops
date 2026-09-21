# InitOps v2.0.0

> **One-command LEMP stack + WordPress deployment engine for Ubuntu 24.04 LTS and Ubuntu 26.04 LTS.**
>
> Optimized for real-world VPS tiers — from 1 GB micro instances to 32 GB+ dedicated servers.

[![Ubuntu](https://img.shields.io/badge/Ubuntu-24.04%20%7C%2026.04%20LTS-E95420?logo=ubuntu&logoColor=white)](https://ubuntu.com/)
[![Nginx](https://img.shields.io/badge/Nginx-1.24+-009639?logo=nginx&logoColor=white)](https://nginx.org/)
[![PHP](https://img.shields.io/badge/PHP-8.3%2F8.4%2F8.5-777BB4?logo=php&logoColor=white)](https://www.php.net/)
[![MariaDB](https://img.shields.io/badge/MariaDB-10.11%20%7C%2011.8-003545?logo=mariadb&logoColor=white)](https://mariadb.org/)
[![Redis](https://img.shields.io/badge/Redis-7.0%20%7C%208.0-DC382D?logo=redis&logoColor=white)](https://redis.io/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

## What is InitOps?

**InitOps** is a single-file, interactive Python CLI that turns a fresh Ubuntu 24.04 or 26.04 server into a production-ready WordPress host in minutes.

No Docker. No Ansible. No 500-line bash scripts. Just run one command, answer a few prompts, and get:

- **LEMP Stack** — Nginx, MariaDB, PHP 8.3/8.4/8.5-FPM, Redis
- **Security Hardening** — iptables firewall, Fail2Ban, socket-only DB/Redis, MariaDB secure installation
- **Auto-Tuned Performance** — 6 hardware profiles (micro → xlarge) with dynamic PHP-FPM sizing and OPcache auto-tuning
- **PHP Version Manager** — Install, switch, and rollback between PHP branches post-deployment with zero downtime
- **Multi-Site Support** — Deploy multiple WordPress sites on the same VPS
- **Discord Monitoring** — Bilingual server health alerts (EN/VI)
- **Domain Migration** — One-shot domain change + SSL + DB search-replace
- **Smart Backups** — WP-CLI exports with gzip + 30-day retention (single or all sites)
- **DNS-01 SSL Auto-Renewal** — Cloudflare DNS challenge for seamless cert renewal

## What's New in v2.0.0

- **Ubuntu 26.04 LTS support** — PHP 8.5 is installed straight from Ubuntu's official repositories, no PPA required. Ubuntu 24.04 works exactly as before.
- **Automatic OS detection** — Runs only on Ubuntu 24.04 and 26.04; anything else stops immediately (both in `install.sh` and in the engine). After an in-place OS upgrade, the menu shows a warning so you can re-apply the configuration.
- **OS-aware Fail2Ban** — iptables on 24.04, nftables + systemd journal on 26.04, followed by a check that the `sshd` jail actually started.
- **MariaDB 11.8 & Redis 8 compatibility** — Removes the deprecated `innodb_buffer_pool_instances`, uses the `mariadb` client, shrinks the unused MyISAM/Aria caches on small tiers, and moves the slow log to `/var/log/mysql` so logrotate covers it.
- **Easier debugging** — PHP-FPM `catch_workers_output` is enabled so PHP errors reach the log instead of vanishing on a 500, and `request_terminate_timeout = 150s` reclaims stuck workers.
- **More resilient deployment** — Waits for the dpkg lock on freshly provisioned VPS, enables the `universe` repository if missing, installs `cron` explicitly, and falls back to the wordpress.org tarball if WP-CLI cannot download WordPress.
- **Accurate PHP support dates** — Active vs. security-only support is now shown correctly for every branch.

## Quick Start

```bash
# Run as root on a fresh Ubuntu 24.04 or 26.04 LTS server
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

Update:

```bash
initops update
```

## Requirements

| Requirement | Details |
|-------------|---------|
| **OS** | Ubuntu 24.04 LTS (Noble Numbat) or Ubuntu 26.04 LTS (Resolute Raccoon) |
| **Privileges** | Root (`sudo` or `root` user) |
| **Network** | Internet access for package installation |
| **RAM** | 1 GB minimum (2 GB+ recommended) |

### Supported Operating Systems

| | Ubuntu 24.04 LTS | Ubuntu 26.04 LTS |
|---|---|---|
| **PHP source** | `ppa:ondrej/php` | Ubuntu's own repositories (no PPA) |
| **PHP versions offered** | 8.3, 8.4 (default), 8.5 | 8.5 only (selected automatically) |
| **MariaDB** | 10.11 | 11.8 |
| **Redis** | 7.0 | 8.0 |
| **Fail2Ban backend** | iptables | nftables + systemd journal |

Other operating systems (including Debian, Linux Mint and non-LTS Ubuntu releases) are not supported and the installer stops immediately.

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
- PHP-FPM `pm.max_children` calculated from actual remaining RAM (after MariaDB + Redis + OS overhead)
- PHP memory limits and realpath cache
- MariaDB `innodb_buffer_pool_size` (up to 45% of RAM, with tier caps)
- Redis `maxmemory` & eviction policies
- OPcache shared memory, interned strings buffer, and max accelerated files

### 2. OPcache Auto-Tuning by Profile

InitOps automatically configures OPcache according to your hardware profile to prevent cache overflow — a common cause of recompile storms and CPU spikes on heavy WordPress themes:

| Profile | OPcache Memory | Interned Strings | Max Files |
|---------|---------------|------------------|-----------|
| `micro` | 96 MB | 16 MB | 30,000 |
| `small` | 192 MB | 24 MB | 50,000 |
| `standard` | 256 MB | 32 MB | 65,000 |
| `medium` | 384 MB | 48 MB | 100,000 |
| `large` / `xlarge` | 512 MB | 64 MB | 130,000 |

OPcache is configured with `validate_timestamps = 1` and `revalidate_freq = 60` for near-zero stat() overhead in production while still applying theme/plugin updates within 60 seconds.

### 3. Kernel & TCP Stack Tuning

InitOps automatically applies a comprehensive kernel tuning set to maximize network throughput, stabilize connections, and accelerate response times:

- **TCP BBR** — Enables the BBR congestion control algorithm instead of Cubic, significantly reducing latency and improving page load speed.
- **File Limits** — Raises `fs.file-max` to 2,000,000 and `fs.inotify.max_user_watches` to 524,288, ensuring Nginx + PHP-FPM are not descriptor-bound under high traffic.
- **Connection Backlog** — Pushes `net.core.somaxconn`, `tcp_max_syn_backlog`, and `netdev_max_backlog` to 65,535, combined with `tcp_syncookies = 1` to mitigate SYN flood / light DDoS spikes.
- **Socket Lifecycle** — Enables `tcp_tw_reuse`, lowers `tcp_fin_timeout` to 15s, fine-tunes keepalive probes (600s / 30s / 5 attempts), and expands `ip_local_port_range` to 1024–65000 for efficient port reuse.
- **Redis Background Save** — Sets `vm.overcommit_memory = 1` to prevent OOM failures when Redis performs BGSAVE on memory-constrained VPS.

All configurations are written to `/etc/sysctl.d/99-initops-kernel.conf` and applied immediately via `sysctl --system` — no reboot required.

### 4. Intelligent Swap Management

InitOps does not create swap rigidly for every profile; instead, it **allocates dynamically based on actual RAM capacity**:

| Profile | RAM Range | Swap Allocation |
|---------|-----------|-----------------|
| `micro` | < 1.5 GB | **2 GB swap file** |
| `small` | 1.5 – 3.5 GB | **2 GB swap file** |
| `standard` | 3.5 – 6 GB | **1 GB swap file** |
| `medium` and above | ≥ 6 GB | **None** — prioritizes keeping workload in physical RAM |

If the system already has an active swap (partition or file), InitOps **auto-detects and skips** to avoid conflicts. The swap file is persisted via `/etc/fstab` with `chmod 600` permissions.

Alongside swap, InitOps tunes two additional critical kernel parameters:

- `vm.swappiness = 10` — Forces the kernel to prioritize RAM usage, only swapping when RAM is critically low (< 10%).
- `vm.vfs_cache_pressure = 50` — Keeps inode/dentry cache in RAM longer, accelerating Nginx and log rotation I/O.

### 5. PHP Version Manager

Manage and switch between PHP branches **after deployment** without reinstalling the entire stack:

| Capability | Description |
|------------|-------------|
| **Install Extra** | Install multiple PHP branches side-by-side — new versions stay inactive (no RAM consumption) until switched |
| **Zero-Downtime Switch** | Start new PHP-FPM alongside the old one, update all vhosts, validate Nginx, then retire the old FPM |
| **Instant Rollback** | Old packages remain installed; one menu action reverts everything |
| **Auto-Reapply Tuning** | Every switch regenerates pool config, runtime INI, and OPcache tuning for the new branch |
| **PHP CLI Sync** | Automatically updates `update-alternatives` so WP-CLI and cron jobs run on the active version |

On **Ubuntu 26.04** only PHP 8.5 is offered (Ubuntu's official repository). If a server was upgraded from 24.04 and still runs an older PHP branch from the PPA, InitOps keeps detecting it correctly, and you can install PHP 8.5 and switch to it with the workflow below.

**Safe switch workflow:**
1. Generate InitOps tuning (pool + runtime + OPcache) for the new PHP branch
2. Validate PHP-FPM config before touching any live service
3. Start `php[new]-fpm` alongside `php[old]-fpm` (both sockets coexist)
4. Rewrite `fastcgi_pass` in all vhosts, run `nginx -t`
5. If `nginx -t` fails → rollback all vhosts immediately, site never goes down
6. Only after nginx reloads successfully, stop and disable `php[old]-fpm`

### 6. Multi-Site on One VPS
Deploy multiple independent WordPress sites on the same server:

- Each site gets its own **database**, **Redis DB index**, and **Nginx vhost**
- Custom web root folder names (`/var/www/<your-folder>`)
- Isolated Redis databases (DB 0 for the first site, DB 1+ for additional sites)
- Per-site WP-Cron via `flock` to prevent overlapping processes
- Backup supports **all sites at once** or **individual selection**

### 7. Security by Default
- **iptables** — Ports 22, 80, 443 only
- **Fail2Ban** — SSH brute-force protection (5 retries / 1h ban), iptables action on 24.04, nftables action on 26.04
- **MariaDB Hardening** — Removes anonymous users, test database, and disables remote root access
- **Socket Mode** — MariaDB & Redis communicate via Unix sockets (no TCP exposure)
- **WP Hardening** — `DISALLOW_FILE_EDIT`, disabled XML-RPC, cron offloaded to system
- **File Permissions** — Directories 755, files 644, `wp-config.php` 640

### 8. Discord Server Monitor
Bilingual (English / Vietnamese) webhook alerting for:
- Disk space critical
- RAM exhaustion
- CPU overload
- MySQL/MariaDB downtime
- Auto-recovery notifications

Profile-aware cron intervals (every 5–10 minutes).

### 9. One-Shot Domain Migration
Change your domain without breaking anything:
- Updates Nginx vhost with **config validation before applying**
- Issues new SSL via Certbot
- Performs precise DB search-replace (respects serialized data)
- Flushes Redis cache automatically
- **Auto-rollback** if Nginx validation fails

### 10. Database Backups
```
/var/backups/wordpress/wp_db_<domain>_<YYYYMMDD_HHMMSS>.sql.gz
```
- WP-CLI export (no password prompts)
- Auto-gzip compression
- Auto-cleanup: deletes backups older than 30 days
- **Multi-site aware** — backup all sites or select individual ones

### 11. DNS-01 SSL Auto-Renewal via Cloudflare
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

### 12. PHP 8.3, 8.4, or 8.5 — Your Choice

InitOps lets you **select your PHP version** during deployment (Ubuntu 24.04) and manage it afterward. On Ubuntu 26.04, PHP 8.5 is selected automatically.

| Version | Status | Support | Best For |
|---------|--------|---------|----------|
| **8.3** | Security fixes only | Security until Dec 2027 | Maximum compatibility |
| **8.4** | Stable, default on 24.04 | Active until Dec 2026, security until Dec 2028 | Production environments, improved JIT |
| **8.5** | Latest, only option on 26.04 | Active until Dec 2027, security until Dec 2029 | Newest features, longest support runway |

After deployment, the system **auto-detects** your running PHP version when you select **Re-apply Performance Optimizations** — no manual edits needed.

## Interactive Menu

```
============================================================
                    InitOps v2.0.0
============================================================
 [System]:              4 CPU Cores | 4096 MB RAM
 [OS]:                  Ubuntu 26.04 LTS
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
 [9] PHP Version Manager (PHP 8.5 from Ubuntu repositories)
 [0] Exit
------------------------------------------------------------
Option (0-9):
```

On Ubuntu 24.04, option `[9]` reads `PHP Version Manager (Install / Switch 8.3 · 8.4 · 8.5)`.

## Configuration Files

| Component | Path |
|-----------|------|
| Nginx Main | `/etc/nginx/nginx.conf` |
| Nginx Vhost (default) | `/etc/nginx/sites-available/wordpress` |
| PHP-FPM Pool | `/etc/php/{8.3,8.4,8.5}/fpm/pool.d/z_custom_pm.conf` |
| PHP Runtime Tuning | `/etc/php/{8.3,8.4,8.5}/fpm/conf.d/99-initops-runtime.ini` |
| OPcache Tuning | `/etc/php/{8.3,8.4,8.5}/fpm/conf.d/98-initops-opcache.ini` |
| PHP-FPM Log | `/var/log/php{8.3,8.4,8.5}-fpm.log` |
| MariaDB Tuning | `/etc/mysql/conf.d/z_custom_optimize.cnf` |
| MariaDB Slow Log | `/var/log/mysql/mariadb-slow.log` |
| Redis Config | `/etc/redis/redis.conf` |
| Fail2Ban Config | `/etc/fail2ban/jail.local` |
| WP Config (default) | `/var/www/html/wp-config.php` |
| Deploy Lock | `/etc/.initops_deployed.lock` |
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
6. *(Recommended)* Check the security services: `fail2ban-client status sshd`

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

## Switching PHP Versions

Use **Option [9]** in the InitOps menu to manage PHP versions:

```bash
initops
# Select [9] PHP Version Manager
```

Available actions:
- **Install** additional PHP branches side-by-side (8.3, 8.4, 8.5 on Ubuntu 24.04; 8.5 on Ubuntu 26.04)
- **Switch** active PHP version with zero downtime and automatic rollback safety
- All vhosts are updated automatically, and OPcache tuning is regenerated for the new branch

## Upgrading from v1.9.x

```bash
initops update
```

Updating replaces the engine only. The new tuning (PHP-FPM logging, MariaDB cache sizing, slow-log path) is applied to an existing server when you run **Option [2] Re-apply Performance Optimizations**.

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

- [Ondřej Surý](https://deb.sury.org/) for the maintained PHP PPA (used on Ubuntu 24.04)
- [Ubuntu](https://ubuntu.com/) for shipping PHP 8.5 natively in 26.04
- [WordPress](https://wordpress.org/) & [WP-CLI](https://wp-cli.org/) teams
- The open-source Nginx, MariaDB, and Redis communities
