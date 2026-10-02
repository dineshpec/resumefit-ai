#!/bin/sh
# Restart ResumeFit containers whose health check is failing.
#
# Docker's restart policy acts only when a container exits, not when it stays up
# but turns unhealthy. Run this from the VPS owner's crontab every minute
# (see README, "Operate"). It needs the docker group, as `docker compose` does,
# but no extra container with access to the Docker socket.
set -eu

for id in $(docker ps --quiet \
    --filter "label=com.docker.compose.project=resumefit" \
    --filter "health=unhealthy"); do
  name=$(docker inspect --format '{{.Name}}' "$id")
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) restarting unhealthy container ${name#/}"
  docker restart "$id" >/dev/null
done
