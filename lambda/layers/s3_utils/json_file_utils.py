"""
MAKI JSON File Processing Utilities Layer

This Lambda layer provides specialized utilities for JSON file processing, 
validation, and formatting within the MAKI S3 data processing pipeline.

Purpose:
- Validate and process JSON files in S3 operations
- Fix common JSON formatting issues in data sources
- Compress and reformat JSON data for efficient storage
- Support both JSON and JSONL file type detection

Key Features:
- JSON and JSONL file type detection
- JSON validation with error handling
- Common typo correction (e.g., "submittedBY" to "submittedBy")
- JSON compression and reformatting
- Multi-object JSON parsing and JSONL conversion

Functions Provided:
- isJsonFile(): File type detection for JSON/JSONL files
- is_valid_json(): Simple JSON validation check
- fix_submitted_by_typo(): Correct common field name typos
- reformatJson(): Complete JSON reformatting pipeline
- compress_json(): JSON compression and JSONL conversion

Data Processing Features:
- Automatic typo correction for known issues
- Multi-object JSON parsing support
- JSONL format conversion for batch processing
- Whitespace and formatting optimization
- Error handling for malformed data

Integration Points:
- S3 operations: File processing and validation
- Data ingestion: Format standardization
- Batch processing: JSONL format preparation
- Error handling: Data quality assurance

Use Cases:
- CID data processing and cleanup
- S3 file format standardization
- Batch inference data preparation
- Data quality validation
- Storage optimization through compression
"""

import json

def isJsonFile(filename):
    """Check if filename is a JSON or JSONL file"""
    return filename.endswith('.json') or filename.endswith('.jsonl')

def is_valid_json(json_string):
    """Validate if string is valid JSON"""
    try:
        json.loads(json_string)
        return True
    except json.JSONDecodeError:
        return False

def fix_submitted_by_typo(data):
    try:
        if data is None:
            return None
        return data.replace('"submittedBY":', '"submittedBy":')
    except Exception as e:
        print("Error fix_submitted_by_typo", str(e))
        return None

def reformatJson(jsonString):
    if jsonString is None:
        return None
    inputData = fix_submitted_by_typo(jsonString)
    return compress_json(inputData)

def compress_json(input_string):
    try:
        if input_string is None:
            return None
        content = input_string.strip()
        
        # Parse multiple JSON objects
        decoder = json.JSONDecoder()
        json_objects = []
        idx = 0
        
        while idx < len(content):
            content = content[idx:].lstrip()
            if not content:
                break
            try:
                obj, end_idx = decoder.raw_decode(content)
                json_objects.append(obj)
                idx += end_idx
            except json.JSONDecodeError:
                break
        
        # Create JSONL output
        output_lines = []
        for obj in json_objects:
            output_lines.append(json.dumps(obj, separators=(',', ':')))
        
        return '\n'.join(output_lines)
        
    except Exception as e:
        print("Error compressing JSON:", str(e))
        return None