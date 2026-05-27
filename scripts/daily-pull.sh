#!/bin/bash
# Pull diario de camilootoya-habi/tableros-marketing-habi para mantener los data.json
# locales sincronizados con los que el workflow genera a las 7am MX.
# Se ejecuta desde cron a las 7:30am MX (30 min después del workflow).
# Log: /tmp/tableros-pull.log
set -eo pipefail
cd "$HOME/habi/tableros-marketing"
echo "=== $(date -Iseconds) ===" >> /tmp/tableros-pull.log
git pull --ff-only origin main >> /tmp/tableros-pull.log 2>&1
