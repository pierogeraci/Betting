#!/bin/sh
# Avvia SeaweedFS con due identità S3: quella interna, completa, e quella di
# raccolta, che può solo scrivere nel secchio di arrivo, e quella di estrazione, che in più
# legge i file da lavorare dal secchio di lavorazione.
set -eu
cat > /tmp/s3.json <<JSON
{"identities":[
 {"name":"interno","credentials":[{"accessKey":"${S3_ACCESS_KEY}","secretKey":"${S3_SECRET_KEY}"}],"actions":["Admin","Read","Write","List","Tagging"]},
 {"name":"raccolta","credentials":[{"accessKey":"${RACCOLTA_S3_ACCESS_KEY}","secretKey":"${RACCOLTA_S3_SECRET_KEY}"}],"actions":["Write:${S3_BUCKET_ARRIVO}"]},
 {"name":"estrazione","credentials":[{"accessKey":"${ESTRAZIONE_S3_ACCESS_KEY}","secretKey":"${ESTRAZIONE_S3_SECRET_KEY}"}],"actions":["Write:${S3_BUCKET_ARRIVO}","Read:${S3_BUCKET_LAVORAZIONE}"]}
]}
JSON
exec weed server -dir=/data -ip.bind=0.0.0.0 -volume.max=50 -master.volumeSizeLimitMB=1024 -s3 -s3.port=8333 -s3.config=/tmp/s3.json
