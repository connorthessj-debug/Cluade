#!/bin/bash
# Generate self-signed TLS certificates for the badge server.
#
# These are for development/internal network use. For production on a
# public network, use Let's Encrypt or your organization's CA.
#
# Usage:
#   cd badge-system
#   bash scripts/generate_certs.sh

set -e

CERT_DIR="server/certs"
mkdir -p "$CERT_DIR"

echo "Generating self-signed TLS certificate..."
echo "This certificate is valid for 365 days."
echo

openssl req -x509 \
    -newkey rsa:2048 \
    -keyout "$CERT_DIR/key.pem" \
    -out "$CERT_DIR/cert.pem" \
    -days 365 \
    -nodes \
    -subj "/CN=badge-server.local/O=Badge System/OU=Internal"

echo
echo "Certificates generated:"
echo "  Certificate: $CERT_DIR/cert.pem"
echo "  Private key: $CERT_DIR/key.pem"
echo
echo "Copy cert.pem to the Raspberry Pi for TLS verification:"
echo "  scp $CERT_DIR/cert.pem pi@<pi-ip>:~/badge-system/server_cert.pem"
echo "  Then set: export BADGE_TLS_CERT=~/badge-system/server_cert.pem"
