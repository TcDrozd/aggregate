#!/bin/sh
# Migrate, then serve. Runs as the container's non-root user.
set -eu

case "${AGGREGATE_DATABASE_URL}" in
    sqlite:////data/*)
        if [ ! -w /data ]; then
            echo "aggregate: /data is not writable by uid $(id -u)." >&2
            echo "On the host, run: sudo chown $(id -u):$(id -g) ./data" >&2
            exit 1
        fi
        ;;
esac

aggregate db upgrade
exec uvicorn aggregate.main:create_app --factory --host 0.0.0.0 --port 8000
