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