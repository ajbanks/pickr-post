#!/usr/bin/bash

source "/home/web/.env"
export PGPASSWORD=$PGPASSWORD

DATABASE="pickr"
GCLOUD_BUCKET="gs://pickr-prod-postgres-backups"
backup_name="${DATABASE}_$(date +'%Y-%m-%dT%H:%M')"

echo -n "==> dumping postgres database ${DATABASE}..."
pg_dump -U pickr_super pickr | zstd -7 > "/backups/${backup_name}.zst"
echo "done"

# keep backups for one week
find /backups -delete -mtime +6 -iname

gcloud storage cp "/backups/$backup_name" $GCLOUD_BUCKET
