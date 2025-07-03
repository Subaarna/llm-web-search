import os
from typing import List
from groq import Groq
import json
import re

def validate_api_key() -> tuple[bool, str]:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return False, "Groq API key not found. Please set the GROQ_API_KEY environment variable."
    if len(api_key) > 20:  # Basic validation
        return True, "Valid API key format"
    return False, "Invalid Groq API key format. Please check your API key."

def extract_list_from_response(content: str) -> List[str]:
    """Extract the list from the model's response, handling various formats."""
    # Try to find a list pattern in the response
    list_pattern = r'\[(.*?)\]'
    match = re.search(list_pattern, content, re.DOTALL)
    
    if match:
        list_str = match.group(0)
        try:
            # Try to parse the extracted list
            return json.loads(list_str)
        except json.JSONDecodeError:
            print(f"\n❌ Error parsing extracted list: {list_str}")
            return []
    return []

def generate_queries(question: str) -> List[str]:
    # Validate API key first
    is_valid, message = validate_api_key()
    if not is_valid:
        print(f"\n❌ Groq API Key Error: {message}")
        print("Please check your .env file and make sure you have a valid Groq API key.")
        return []

    try:
        client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        
        response = client.chat.completions.create(
            model="qwen-qwq-32b",  # Using Qwen model
            messages=[
                {"role": "system", "content": "You are a helpful assistant that generates search queries. Always respond with ONLY a JSON array of strings, nothing else."},
                {"role": "user", "content": PROMPT_TEMPLATE.format(question=question)}
            ],
            temperature=0.3
        )
        content = response.choices[0].message.content
        
        # Try to parse the entire response first
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            # If that fails, try to extract just the list part
            queries = extract_list_from_response(content)
            if queries:
                return queries
            else:
                print(f"\n❌ Could not extract valid queries from response")
                print(f"Raw response: {content}")
                return []
            
    except Exception as e:
        print(f"\n❌ Error when calling Groq API: {str(e)}")
        print("Please check your API key and connection.")
        return []


PROMPT_TEMPLATE = """
Break the following question into 3 to 5 effective search queries that could be used in a web search engine.

Question:
{question}

Return ONLY a JSON array of strings, like this:
["query one", "query two", "query three"]
No other text, explanation, or thinking process should be included.
"""
