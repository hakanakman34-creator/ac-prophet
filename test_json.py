import re

def extract_json(text: str) -> str:
    # try to find json block
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        return match.group(1)
    
    # fallback: try to find first { and last }
    start = text.find('{')
    end = text.rfind('}')
    if start != -1 and end != -1:
        return text[start:end+1]
    
    return text

import json
print(extract_json("Some text <think>thinking...</think> ```json\n{\"test\": 123}\n```"))
print(extract_json("<think>hello</think>\n{\"a\": 1}"))
