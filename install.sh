#!/bin/bash
# -------------------------------------------------------------------------
# InitOps v1.4.0 - Automated LEMP & WordPress Deployment Engine
# -------------------------------------------------------------------------

if [ "$EUID" -ne 0 ]; then
  echo -e "\e[1;31m[ERROR]\e[0m Please run this script with root privileges (sudo)."
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive

echo -e "\e[1;32m[*] Updating system and installing Python3...\e[0m"
apt-get update -y > /dev/null 2>&1
apt-get install -y python3 curl > /dev/null 2>&1

echo -e "\e[1;32m[*] Fetching InitOps setup engine...\e[0m"
curl -fsSL -H "Cache-Control: no-cache" "https://inithtml.com/initops/setup.py?v=$(date +%s)" -o /usr/local/bin/initops

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