#!/usr/bin/env bash
set -euo pipefail

export LC_ALL=C

temp_dir="$(mktemp -d)"
data_dir="$temp_dir/data"
server_started=0
cleanup() {
  if [[ "$server_started" == 1 ]]; then
    pg_ctl -D "$data_dir" -m immediate -w stop >/dev/null
  fi
  rm -rf "$temp_dir"
}
trap cleanup EXIT

initdb -D "$data_dir" -U postgres --encoding=UTF8 --no-instructions >/dev/null
port="$(python3 -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')"
pg_ctl -D "$data_dir" -o "-h 127.0.0.1 -p $port -c unix_socket_directories=''" -w start >/dev/null
server_started=1

database_url="postgresql://postgres@127.0.0.1:$port/postgres"
psql "$database_url" -v ON_ERROR_STOP=1 -f supabase/tests/local_auth_stub.sql
for migration in supabase/migrations/*.sql; do
  psql "$database_url" -v ON_ERROR_STOP=1 -1 -f "$migration"
done
psql "$database_url" -v ON_ERROR_STOP=1 -f supabase/tests/rls_test.sql
TEST_DATABASE_URL="$database_url" python3 -m unittest tests.test_db -v
