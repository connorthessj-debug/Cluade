#!/bin/bash
# WireGuard VPN setup for secure communication between the Raspberry Pi
# and the Gutenberg badge server on different networks.
#
# WireGuard creates an encrypted tunnel so the Pi and server can communicate
# as if they're on the same network, even across the internet.
#
# Run this script on BOTH the Pi and the server to generate keys,
# then manually configure each side with the other's public key.
#
# Usage:
#   bash scripts/setup_wireguard.sh [server|pi]

set -e

ROLE="${1:-}"
if [ -z "$ROLE" ] || { [ "$ROLE" != "server" ] && [ "$ROLE" != "pi" ]; }; then
    echo "Usage: $0 [server|pi]"
    echo
    echo "Run with 'server' on the Gutenberg PC, 'pi' on the Raspberry Pi."
    echo "Then exchange public keys between the two."
    exit 1
fi

echo "=== WireGuard Setup ($ROLE) ==="
echo

# Check if WireGuard is installed
if ! command -v wg &> /dev/null; then
    echo "WireGuard not found. Installing..."
    if [ -f /etc/debian_version ]; then
        sudo apt update && sudo apt install -y wireguard
    elif [ -f /etc/fedora-release ]; then
        sudo dnf install -y wireguard-tools
    elif [ -f /etc/arch-release ]; then
        sudo pacman -S --noconfirm wireguard-tools
    else
        echo "Please install WireGuard manually for your OS."
        echo "See: https://www.wireguard.com/install/"
        exit 1
    fi
fi

# Generate keys
echo "Generating WireGuard keys..."
PRIVATE_KEY=$(wg genkey)
PUBLIC_KEY=$(echo "$PRIVATE_KEY" | wg pubkey)

echo "  Private key: (saved to config, keep secret!)"
echo "  Public key:  $PUBLIC_KEY"
echo
echo "Share this public key with the other machine."
echo

if [ "$ROLE" = "server" ]; then
    # Server config
    # VPN IP: 10.0.0.1 for server, 10.0.0.2 for Pi
    CONFIG="/etc/wireguard/wg-badge.conf"

    cat << EOF
=== SERVER CONFIGURATION ===

Save the following to $CONFIG (requires sudo):

[Interface]
Address = 10.0.0.1/24
ListenPort = 51820
PrivateKey = $PRIVATE_KEY

[Peer]
# Raspberry Pi
PublicKey = <PASTE PI PUBLIC KEY HERE>
AllowedIPs = 10.0.0.2/32

---

Then run:
  sudo wg-quick up wg-badge

The badge server should listen on 10.0.0.1:5000.
Set the Pi's BADGE_SERVER_URL to: https://10.0.0.1:5000

IMPORTANT: Open port 51820/UDP on your firewall/router for incoming
WireGuard connections from the Pi's network.
EOF

elif [ "$ROLE" = "pi" ]; then
    CONFIG="/etc/wireguard/wg-badge.conf"

    cat << EOF
=== RASPBERRY PI CONFIGURATION ===

Save the following to $CONFIG (requires sudo):

[Interface]
Address = 10.0.0.2/24
PrivateKey = $PRIVATE_KEY

[Peer]
# Badge Server
PublicKey = <PASTE SERVER PUBLIC KEY HERE>
Endpoint = <SERVER_PUBLIC_IP>:51820
AllowedIPs = 10.0.0.1/32
PersistentKeepalive = 25

---

Then run:
  sudo wg-quick up wg-badge

Set the following environment variable:
  export BADGE_SERVER_URL=https://10.0.0.1:5000

To auto-start on boot:
  sudo systemctl enable wg-quick@wg-badge
EOF
fi

echo
echo
echo "=== Quick Test ==="
echo "After configuring both sides, test connectivity with:"
if [ "$ROLE" = "server" ]; then
    echo "  ping 10.0.0.2  (should reach the Pi)"
else
    echo "  ping 10.0.0.1  (should reach the server)"
fi
