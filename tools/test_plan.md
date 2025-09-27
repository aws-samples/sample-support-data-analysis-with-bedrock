## Deploy
cdk synth MakiFoundations
cdk deploy MakiFoundations --require-approvals never
cdk synth MakiData
cdk deploy MakiData --require-approvals never
cdk synth MakiEmbeddings
cdk deploy MakiEmbeddings --require-approvals never

## Purge s3 buckets
python tools/purge_s3_data.py

## Test Cases / Empty
python tools/flip_mode.py --mode cases


