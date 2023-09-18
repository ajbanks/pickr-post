#!/usr/bin/bash

source "/home/web/.env"

DATABASE="pickr"
GCLOUD_BUCKET="gs://pickr-prod-postgres-backups"
backup_name="${DATABASE}_$(date +'%Y-%m-%dT%H:%M')"

echo -n "==> dumping postgres database ${DATABASE}..."
PGPASSWORD=$PGPASSWORD pg_dump -U pickr_super pickr | zstd -7 > "/backups/${backup_name}.zst"
echo "done"

# keep backups for one week
find /backups -delete -mtime +6 -iname 'pickr.*zst'

gcloud storage cp "/backups/$backup_name" $GCLOUD_BUCKET
