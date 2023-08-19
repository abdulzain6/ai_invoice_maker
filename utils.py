import json
import re

def extract_number_and_convert_to_float(text: str) -> float:
    if numbers := re.findall(r'\d+\.?\d*', text):
        return float(numbers[0])
    else:
        return None
    
def read_password_from_json(filepath: str) -> str:
    with open(filepath, 'r') as file:
        data = json.load(file)
        return data.get('password')
