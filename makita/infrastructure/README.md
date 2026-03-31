# Makita DR Reference - Infrastructure

Sample RDS Postgres setup for the DR reference architecture.

## Deployment Order

### 1. Deploy Primary RDS (us-east-1)

```bash
aws cloudformation deploy \
  --template-file rds-primary.yaml \
  --stack-name makita-dr-primary \
  --region us-east-1 \
  --parameter-overrides \
    DBMasterUsername=makitaadmin \
    DBMasterPassword=<your-password> \
    VpcId=<your-vpc-id> \
    SubnetIds=<subnet-1>,<subnet-2>
```

Wait for the primary instance to become available (~10 min):

```bash
aws rds wait db-instance-available \
  --db-instance-identifier makita-dr-primary \
  --region us-east-1
```

### 2. Deploy Cross-Region Replica (us-east-2)

Get the primary ARN from the stack output:

```bash
PRIMARY_ARN=$(aws cloudformation describe-stacks \
  --stack-name makita-dr-primary \
  --region us-east-1 \
  --query 'Stacks[0].Outputs[?OutputKey==`PrimaryArn`].OutputValue' \
  --output text)
```

Deploy the replica:

```bash
aws cloudformation deploy \
  --template-file rds-replica.yaml \
  --stack-name makita-dr-replica \
  --region us-east-2 \
  --parameter-overrides \
    SourceDBInstanceArn=$PRIMARY_ARN \
    VpcId=<your-vpc-id-in-us-east-2> \
    SubnetIds=<subnet-1>,<subnet-2>
```

### 3. Deploy SSM Parameters (us-east-1)

```bash
aws cloudformation deploy \
  --template-file ssm-parameters.yaml \
  --stack-name makita-dr-parameters \
  --region us-east-1 \
  --parameter-overrides \
    SlackBotToken=<your-slack-bot-token> \
    ServiceNowApiKey=<your-api-key>
```

## Cleanup

```bash
aws cloudformation delete-stack --stack-name makita-dr-replica --region us-east-2
aws rds wait db-instance-deleted --db-instance-identifier makita-dr-replica --region us-east-2
aws cloudformation delete-stack --stack-name makita-dr-primary --region us-east-1
aws cloudformation delete-stack --stack-name makita-dr-parameters --region us-east-1
```

## What Gets Created

| Resource | Region | Name |
|----------|--------|------|
| RDS Postgres 16.4 (db.t3.micro) | us-east-1 | makita-dr-primary |
| RDS Cross-Region Read Replica | us-east-2 | makita-dr-replica |
| DB Subnet Groups | both | makita-dr-*-subnet-group |
| Security Groups (port 5432, 10.0.0.0/8) | both | makita-dr-*-sg |
| SSM Parameters (/makita-dr/*) | us-east-1 | 18 parameters |

Both instances use `db.t3.micro` with 20GB encrypted storage to keep costs minimal for a reference demo.
