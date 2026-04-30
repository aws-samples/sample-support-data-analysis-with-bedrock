# MAKI Test Plan

## Usage
Run the test plan with: `python maki/tools/execute_test_plan.py`

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
python maki/tools/runMaki.py
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
python maki/tools/generate_synth_cases.py --min-cases 5 --max-cases 10
```

you can use the below th store cases in s3://maki-temp, and copy them over

```
python maki/tools/copy_s3_data.py from-temp 
```

## End Usage

## Test 1: Cases / Empty
python maki/tools/purge_s3_data.py
python maki/tools/flip_mode.py --mode cases
python maki/tools/runMaki.py
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
  "Event_Example*": "*"
}
### END OUTPUT

## Test 2: Cases / OnDemand
python maki/tools/purge_s3_data.py
python maki/tools/flip_mode.py --mode cases
python maki/tools/generate_synth_cases.py -q
python maki/tools/runMaki.py
### OUTPUT
{
  "Summary": {
    "*": "*"
  },
  "Event_Example*": "*"
}
### END OUTPUT

## Test 3: Cases / Batch
python maki/tools/purge_s3_data.py
python maki/tools/flip_mode.py --mode cases
<!-- this can take a while, you can use pre-generated cases. -->   
python maki/tools/generate_synth_cases.py --min-cases 7 --max-cases 8 
<!-- the below copies pre-generated cases from s3://maki-temp 
see the MAKI_USER_GUIDE.md for more details
python maki/tools/copy_s3_data.py from-temp 
-->
python maki/tools/runMaki.py
### OUTPUT
{
  "Summary": {
    "summary": "*"
  },
  "Event_Example*": "*"
}
### END OUTPUT

## Test 4: Health / Empty
python maki/tools/purge_s3_data.py
python maki/tools/flip_mode.py --mode health
python maki/tools/opensearch_client.py --size 0
python maki/tools/runMaki.py
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
  "Event_Example*": "*"
}
### END OUTPUT

## Test 5: Health / OnDemand
python maki/tools/generate_synth_health_events.py --synth 10
python maki/tools/purge_s3_data.py
python maki/tools/flip_mode.py --mode health
python maki/tools/opensearch_client.py --endpoint
python maki/tools/opensearch_client.py --size 5 
python maki/tools/runMaki.py
### OUTPUT
{
  "Summary": {
    "summary": "*"
  },
  "Event_Example*": "*"
}
### END OUTPUT

## Test 6: Health / Batch
python maki/tools/generate_synth_health_events.py --synth 150
python maki/tools/purge_s3_data.py
python maki/tools/flip_mode.py --mode health
python maki/tools/opensearch_client.py --endpoint
python maki/tools/opensearch_client.py --size 120
python maki/tools/runMaki.py
### OUTPUT
{
  "Summary": {
    "summary": "*"
  },
  "Event_Example*": "*"
}
### END OUTPUT
