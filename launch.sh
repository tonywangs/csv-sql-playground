#!/bin/sh
set -eu
cd "$(dirname "$0")"
echo 'Open http://127.0.0.1:8876/web/ (Ctrl-C to stop)'
exec python3 -m http.server 8876 --bind 127.0.0.1
