# MAKI Test Plan

## Usage
Run the test plan with: `python tools/execute_test_plan.py`

### File Format
- Commands are organized under `## Section Name` headers
- Each command should be on its own line
- Comment out commands using HTML comments: `<!--command-->`
- Add expected output validation using:
  ```
  ### OUTPUT
  expected output pattern (use * for wildcards)
  ### END OUTPUT
  ```
- Output validation applies only to the immediately preceding command

### Examples
```
## Deploy
cdk synth MakiFoundations
<!--cdk deploy MakiFoundations --require-approvals never-->

## Test
python tools/runMaki.py
### OUTPUT
{
  "status": "*"
}
### END OUTPUT
```

### Batch Testing Optimization
For Test Cases / Batch, to save time generating many cases repeatedly:

rather than using the below to generate the cases
```
python tools/generate_synth_cases.py --min-cases 5 --max-cases 10
```

you can use the below th store cases in s3://maki-temp, and copy them over

```
python tools/copy_s3_data.py from-temp 
```

## End Usage

## Test 1: Deploy
cdk synth MakiFoundations
cdk deploy MakiFoundations --require-approvals never
cdk synth MakiData
cdk deploy MakiData --require-approvals never 
cdk synth MakiEmbeddings
cdk deploy MakiEmbeddings --require-approvals never

## Test 2: Cases / Empty
python tools/purge_s3_data.py
python tools/flip_mode.py --mode cases
python tools/runMaki.py
### OUTPUT
{
  "Summary": {
    "eventsTotal": 0,
    "events": [],
    "ondemand_run_datetime": "*",
    "mode": "*",
    "status": {
      "status": "*"
    }
  },
  "Event_Example": "*"
}
### END OUTPUT

## Test 3: Cases / OnDemand
python tools/purge_s3_data.py
python tools/flip_mode.py --mode cases
python tools/generate_synth_cases.py -q
python tools/runMaki.py
### OUTPUT
{
  "Summary": {
    "summary": "*"
  },
  "Event_Example": {
    "caseId": "*",
    "displayId": "*",
    "status": "*",
    "serviceCode": "*",
    "timeCreated": "*",
    "timeResolved": *,
    "submittedBy": "*",
    "category": "*",
    "category_explanation": "*",
    "case_summary": "*",
    "sentiment": "*",
    "suggested_action": "*",
    "suggestion_link": "*"
  }
}
### END OUTPUT

## Test 4: Cases / Batch
python tools/purge_s3_data.py
python tools/flip_mode.py --mode cases
python tools/copy_s3_data.py from-temp 
python tools/runMaki.py
### OUTPUT
{
  "Summary": {
    "summary": "*"
  },
  "Event_Example": {
    "caseId": "*",
    "displayId": "*",
    "status": "*",
    "serviceCode": "*",
    "timeCreated": "*",
    "timeResolved": *,
    "submittedBy": "*",
    "category": "*",
    "category_explanation": "*",
    "case_summary": "*",
    "sentiment": "*",
    "suggested_action": "*",
    "suggestion_link": "*"
  }
}
### END OUTPUT

## Test 5: Health / Empty
python tools/purge_s3_data.py
python tools/flip_mode.py --mode health
python tools/opensearch_client.py --size 0
python tools/runMaki.py
### OUTPUT
{
  "Summary": {
    "eventsTotal": 0,
    "events": [],
    "ondemand_run_datetime": "*",
    "mode": "health",
    "status": {
      "status": "Execution stopped: no events were found to process"
    }
  },
  "Event_Example": "No individual event files found"
}
### END OUTPUT

## Test 6: Health / OnDemand
python tools/purge_s3_data.py
python tools/flip_mode.py --mode health
python tools/opensearch_client.py --endpoint
python tools/opensearch_client.py --size 1 
python tools/runMaki.py
### OUTPUT
{
  "Summary": {
    "summary": "*"
  },
  "Event_Example": {
    "arn": "*",
    "service": "*",
    "eventTypeCode": "*",
    "eventTypeCategory": "*",
    "region": "*",
    "startTime": "*",
    "lastUpdatedTime": "*",
    "statusCode": "*",
    "eventScopeCode": "*",
    "latestDescription": "*",
    "event_summary": "*",
    "suggestion_action": "*",
    "suggestion_link": "*"
  }
}
### END OUTPUT

## Test 7: Health / Batch
python tools/purge_s3_data.py
python tools/flip_mode.py --mode health
python tools/opensearch_client.py --endpoint
python tools/opensearch_client.py --size 101 
python tools/runMaki.py
### OUTPUT
{
  "Summary": {
    "summary": "*"
  },
  "Event_Example": {
    "arn": "*",
    "service": "*",
    "eventTypeCode": "*",
    "eventTypeCategory": "*",
    "region": "*",
    "startTime": "*",
    "lastUpdatedTime": "*",
    "statusCode": "*",
    "eventScopeCode": "*",
    "latestDescription": "*",
    "event_summary": "*",
    "suggestion_action": "*",
    "suggestion_link": "*"
  }
}
### END OUTPUT
