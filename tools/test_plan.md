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
## End Usage

## Deploy
<!--
cdk synth MakiFoundations
cdk deploy MakiFoundations --require-approvals never
cdk synth MakiData
cdk deploy MakiData --require-approvals never 
cdk synth MakiEmbeddings
cdk deploy MakiEmbeddings --require-approvals never
-->

## Test Cases / Empty
<!--
python tools/purge_s3_data.py
python tools/flip_mode.py --mode cases
python tools/runMaki.py
### OUTPUT
{
  "Summary": {
    "eventsTotal": 0,
    "events": [],
    "ondemand_run_datetime": "*",
    "status": {
      "status": "Execution stopped: no events were found to process"
    }
  },
  "Event_Example": "No individual event files found"
}
### END OUTPUT
-->
<!--
## Test Cases / OnDemand
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
-->

## Test Cases / Batch
python tools/purge_s3_data.py
python tools/flip_mode.py --mode cases
<!-- rather than generating many cases every time, store 100+ cases in s3://maki-temp to save time and run the below copy script
python tools/generate_synth_cases.py --min-cases 5 --max-cases 10
-->
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
