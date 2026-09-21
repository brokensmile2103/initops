#!/bin/bash
# -------------------------------------------------------------------------
# InitOps v2.0.0 - Automated LEMP & WordPress Deployment Engine
# Supported: Ubuntu 24.04 LTS and Ubuntu 26.04 LTS
# -------------------------------------------------------------------------

if [ "$EUID" -ne 0 ]; then
  echo -e "\e[1;31m[ERROR]\e[0m Please run this script with root privileges (sudo)."
  exit 1
fi

# Fail fast on an unsupported OS, before touching apt. (setup.py re-checks the
# same thing, this just saves the download and package round-trip.)
OS_ID="$( . /etc/os-release 2>/dev/null && echo "$ID" )"
OS_VERSION_ID="$( . /etc/os-release 2>/dev/null && echo "$VERSION_ID" )"
OS_PRETTY="$( . /etc/os-release 2>/dev/null && echo "$PRETTY_NAME" )"

if [ "$OS_ID" != "ubuntu" ] || { [ "$OS_VERSION_ID" != "24.04" ] && [ "$OS_VERSION_ID" != "26.04" ]; }; then
  echo -e "\e[1;31m[ERROR]\e[0m Unsupported operating system: ${OS_PRETTY:-unknown}"
  echo "       InitOps 2.0.0 supports Ubuntu 24.04 LTS and Ubuntu 26.04 LTS. Aborting."
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
export NEEDRESTART_MODE=a

# Wait (up to 5 min) for the dpkg lock instead of failing instantly: on a freshly
# provisioned VPS, unattended-upgrades / cloud-init often hold it for a few minutes.
APT_GET="apt-get -o DPkg::Lock::Timeout=300"

echo -e "\e[1;32m[*] Detected ${OS_PRETTY}. Updating system and installing Python3...\e[0m"
$APT_GET update -y > /dev/null 2>&1
$APT_GET install -y python3 curl ca-certificates > /dev/null 2>&1

if ! command -v python3 > /dev/null 2>&1 || ! command -v curl > /dev/null 2>&1; then
  echo -e "\e[1;31m[ERROR]\e[0m Could not install python3 / curl. Run '$APT_GET install -y python3 curl' to see the apt error."
  exit 1
fi

echo -e "\e[1;32m[*] Fetching InitOps setup engine...\e[0m"
curl -fsSL -H "Cache-Control: no-cache" "https://raw.githubusercontent.com/brokensmile2103/initops/main/setup.py" -o /usr/local/bin/initops

if [ ! -f /usr/local/bin/initops ]; then
  echo -e "\e[1;31m[ERROR]\e[0m Failed to download setup engine. Verify network connection."
  exit 1
fi

sed -i 's/\r$//' /usr/local/bin/initops
sed -i 's/\r//g' /usr/local/bin/initops

if ! python3 -c "import ast; ast.parse(open('/usr/local/bin/initops').read())" 2>/dev/null; then
  echo -e "\e[1;31m[ERROR]\e[0m Downloaded file is corrupted or contains syntax errors. Please try again."
  rm -f /usr/local/bin/initops
  exit 1
fi

chmod +x /usr/local/bin/initops

echo -e "\e[1;32m[*] InitOps installed successfully!\e[0m"
echo -e "\e[1;36m[*] Tip: In the future, just type 'initops' anywhere to relaunch the menu.\e[0m"
sleep 2

/usr/local/bin/initops
