"""
MAKI JSON and JSONL Validation Utilities Layer

This Lambda layer provides comprehensive utilities for JSON and JSONL (JSON Lines) 
data validation, conversion, and manipulation throughout the MAKI processing pipeline.

Purpose:
- Validate JSON and JSONL data integrity
- Convert between different JSON formats (JSON, JSONL, dictionaries)
- Provide robust error handling for malformed data
- Support batch processing data validation requirements

Key Features:
- String to dictionary conversion with multiple parsing strategies
- JSON to JSONL format conversion for Bedrock batch processing
- Dictionary to JSONL conversion for data pipeline integration
- JSONL to dictionary parsing for data extraction
- Comprehensive validation with detailed error reporting
- File-based JSONL validation for large datasets

Functions Provided:
- string_to_dict(): Convert string representations to dictionaries
- json_to_jsonl(): Convert JSON strings to JSONL format
- dict_to_jsonl(): Convert dictionaries to JSONL strings
- jsonl_to_dict(): Parse JSONL strings into dictionaries
- json_to_dict(): Convert JSON strings to dictionaries
- validate_jsonl_file(): Validate JSONL files with required key checking
- validate_jsonl(): Validate JSONL strings with error details
- is_valid_json(): Simple JSON validation check

Data Format Support:
- JSON: Standard JSON object and array formats
- JSONL: JSON Lines format (one JSON object per line)
- Dictionary: Python dictionary objects
- String representations: Various string-encoded data formats

Error Handling:
- Graceful handling of malformed JSON data
- Detailed error reporting with line numbers and content
- Multiple parsing strategies (json.loads, ast.literal_eval)
- Comprehensive validation feedback

Integration Points:
- Bedrock batch inference: JSONL format requirements
- S3 data processing: File format validation
- Lambda functions: Data integrity checks
- Prompt generation: Input data validation

Use Cases:
- Validating support case data from CID
- Converting health events for batch processing
- Ensuring data integrity in processing pipelines
- Debugging malformed data issues
"""

import json

def string_to_dict(input_string):
    """
    Convert a string representation of a dictionary to an actual dictionary
    
    Parameters:
        input_string: String containing dictionary-like data
        
    Returns:
        Dictionary if conversion is successful, None otherwise
    """
    try:
        # Try to parse as JSON first
        result_dict = json.loads(input_string)
        
        # Verify we got a dictionary
        if not isinstance(result_dict, dict):
            print("Error: Input does not represent a dictionary")
            return None
            
        return result_dict
        
    except json.JSONDecodeError:
        # If JSON parsing fails, try using ast.literal_eval
        try:
            import ast
            result_dict = ast.literal_eval(input_string)
            
            # Verify we got a dictionary
            if not isinstance(result_dict, dict):
                print("Error: Input does not represent a dictionary")
                return None
                
            return result_dict
            
        except (ValueError, SyntaxError) as e:
            print(f"Error converting string to dictionary: {e}")
            return None


def json_to_jsonl(json_string):
    """
    Convert JSON string to JSONL format
    
    Parameters:
        json_string: String containing JSON data
    
    Returns:
        String in JSONL format
    """
    try:
        # Parse JSON string
        data = json.loads(json_string)
        
        # Handle different JSON structures
        if isinstance(data, dict):
            # Single object - convert directly to JSONL
            return json.dumps(data)
        elif isinstance(data, list):
            # Array of objects - convert each to JSONL
            return '\n'.join(json.dumps(item) for item in data)
        else:
            raise ValueError("JSON must contain an object or array of objects")
            
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON: {e}")
        return None
    except Exception as e:
        print(f"Error converting to JSONL: {e}")
        return None

def dict_to_jsonl(dictionary):
    """
    Convert a dictionary to JSONL string
    
    Parameters:
        dictionary: Dictionary to convert
    
    Returns:
        String in JSONL format
    """
    try:
        # Convert dictionary to JSONL string
        return json.dumps(dictionary)
    except Exception as e:
        print(f"Error converting dictionary to JSONL: {e}")
        return None

def jsonl_to_dict(jsonl_string):
    """
    Convert JSONL string to Python dictionary
    Returns a dictionary containing the parsed JSON objects
    """
    result_dict = {}
    
    try:
        for line in jsonl_string.split('\n'):
            if not line.strip():  # Skip empty lines
                continue
                
            data = json.loads(line.strip())
            if isinstance(data, dict):
                result_dict.update(data)
            
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON: {e}")
        return None
        
    return result_dict

def json_to_dict(json_string):
    """
    Convert JSON string to Python dictionary
    
    Parameters:
        json_string: String containing JSON data
    
    Returns:
        Dictionary containing the parsed JSON object
        None if parsing fails
    """
    try:
        result_dict = json.loads(json_string)
        
        # Verify we got a dictionary
        if not isinstance(result_dict, dict):
            print("Error: JSON root is not an object")
            return None
            
        return result_dict
        
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON: {e}")
        return None

def validate_jsonl_file(file_path, required_keys=None):
    if required_keys is None:
        required_keys = set()
    
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            for line_number, line in enumerate(file, start=1):
                if not line.strip():
                    continue
                    
                try:
                    # Attempt to parse each line as JSON
                    json_data = json.loads(line.strip())
                    
                    # Check if it's a dictionary
                    if not isinstance(json_data, dict):
                        print(f"Line {line_number}: Not a valid JSON object")
                        continue
                        
                    # Check required keys if specified
                    if required_keys and not required_keys.issubset(json_data.keys()):
                        missing = required_keys - json_data.keys()
                        print(f"Line {line_number}: Missing required keys: {missing}")
                        
                except json.JSONDecodeError as e:
                    print(f"Line {line_number}: Invalid JSON - {str(e)}")
                    print(f"Problem line: {line.strip()}")
                    
    except FileNotFoundError:
        print(f"Error: File '{file_path}' not found")
    except UnicodeDecodeError:
        print(f"Error: File '{file_path}' is not in UTF-8 encoding")

def validate_jsonl(jsonl_string):
    """
    Validate if a string is proper JSONL
    
    Parameters:
        jsonl_string: String to validate
    
    Returns:
        tuple: (is_valid: bool, error_info: dict)
    """
    if not jsonl_string or not isinstance(jsonl_string, str):
        return False, {"error": "Input must be a non-empty string"}
    
    error_info = {
        "is_valid": True,
        "line_count": 0,
        "errors": []
    }
    
    try:
        for line_number, line in enumerate(jsonl_string.split('\n'), 1):
            if not line.strip():  # Skip empty lines
                continue
                
            try:
                # Attempt to parse each line as JSON
                data = json.loads(line.strip())
                
                # Verify it's a dictionary/object
                if not isinstance(data, dict):
                    error_info["errors"].append({
                        "line": line_number,
                        "error": "Line is not a JSON object",
                        "content": line.strip()
                    })
                    error_info["is_valid"] = False
                
                error_info["line_count"] += 1
                    
            except json.JSONDecodeError as e:
                error_info["errors"].append({
                    "line": line_number,
                    "error": str(e),
                    "content": line.strip()
                })
                error_info["is_valid"] = False
                
        return error_info["is_valid"], error_info
        
    except Exception as e:
        return False, {"error": f"Unexpected error: {str(e)}"}
    
def is_valid_json(json_string: str) -> bool:
    """
    Check if a string is valid JSON.
    
    Parameters:
        json_string: String to validate as JSON
        
    Returns:
        bool: True if valid JSON, False otherwise
    """
    try:
        json.loads(json_string)
        return True
    except json.JSONDecodeError:
        return False 