import os
import json
import re
from typing import List, Dict, Any
from groq import Groq

#prompt to synthesize the answer
SYNTHESIZE_PROMPT = """
Write a concise answer (MAXIMUM 80 words) to the following question using only the provided search results.

Question: {question}

Search Results:
{documents}

Requirements:
1. MUST be 80 words or less
2. MUST use citation numbers [1][2] etc. to cite sources
3. MUST be factual and based only on the provided sources
4. MUST be clear and well-structured
5. Focus on key differences and practical use cases

IMPORTANT: Return a SINGLE LINE of valid JSON with NO newlines or extra whitespace. Format:
{{"answer":"Your concise answer with citations like [1][2]","citations":[{{"id":1,"title":"Source Title","url":"https://..."}}]}}
"""

#function to format the documents into a string for the prompt
def format_documents(docs: List[Dict[str, Any]]) -> str:
    """Format documents into a string for the prompt."""
    formatted_docs = []
    #loop through the documents and format them
    for i, doc in enumerate(docs, 1):
        formatted_docs.append(
            #format the documents into a string for the prompt
            f"[{i}] Title: {doc['title']}\n"

            f"URL: {doc['url']}\n"
            
            f"Content: {doc['snippet']}\n"
        )
    return "\n".join(formatted_docs)

#function to extract the json from the response, 
def extract_json_from_response(content: str) -> Dict[str, Any]:
    """Extract and validate JSON from the response."""
    # Remove any non-JSON content
    content = content.strip()
    
    # Find anything that looks like JSON with proper nesting
    #regex to find the json in the response
    json_pattern = r'\{(?:[^{}]|(?:\{(?:[^{}]|(?:\{[^{}]*\})*)*\}))*\}'
    matches = re.finditer(json_pattern, content)
    last_match = None
    #loop through the matches and find the last match
    for match in matches:
        last_match = match
    
    if not last_match:
        raise ValueError(f"No JSON object found in response: {content}")
    
    #try to parse the json
    try:
        json_str = last_match.group(0)
        # Aggressive cleanup
        json_str = re.sub(r'[\n\r\t]', '', json_str)  # Remove all newlines, returns, tabs
        json_str = re.sub(r'\s+', ' ', json_str)  # Normalize spaces
        json_str = re.sub(r'([{,])\s+', r'\1', json_str)  # Remove spaces after { and ,
        json_str = re.sub(r'\s+([},])', r'\1', json_str)  # Remove spaces before } and ,
        json_str = json_str.strip()
        
        # Try to parse
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        print(f"\n❌ Error parsing cleaned JSON: {str(e)}")
        print(f"Cleaned JSON string: {json_str}")
        raise

#function to validate the synthesis result by checking the word count and the citations
def validate_synthesis_result(result: Dict[str, Any], docs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Validate and normalize synthesis result."""
    # Create a default valid result
    valid_result = {
        "answer": "Error processing response",
        "citations": []
    }
    
    try:
        # Validate answer
        if isinstance(result.get("answer"), str) and result["answer"]:
            # Check word count
            if len(result["answer"].split()) <= 80:
                valid_result["answer"] = result["answer"]
            else:
                valid_result["answer"] = " ".join(result["answer"].split()[:80]) + "..."
        
        # Validate citations
        if isinstance(result.get("citations"), list):
            valid_citations = []
            for citation in result["citations"]:
                if not isinstance(citation, dict):
                    continue
                
                # Validate each citation field
                if all(isinstance(citation.get(field), expected_type) 
                      for field, expected_type in [("id", int), ("title", str), ("url", str)]):
                    # Ensure citation id is valid
                    if 1 <= citation["id"] <= len(docs):
                        # Get the actual document
                        doc = docs[citation["id"] - 1]
                        # Create a valid citation with actual document data
                        valid_citations.append({
                            "id": citation["id"],
                            "title": doc["title"],
                            "url": doc["url"]
                        })
            
            if valid_citations:
                valid_result["citations"] = valid_citations
                
            # Ensure all citations in answer have corresponding entries
            used_citations = set(int(num) for num in re.findall(r'\[(\d+)\]', valid_result["answer"]))
            defined_citations = set(c["id"] for c in valid_citations)
            
            # Remove citations not used in the answer
            valid_result["citations"] = [c for c in valid_citations if c["id"] in used_citations]
            
            # If no valid citations remain, mark the answer as an error
            if not valid_result["citations"] and used_citations:
                valid_result["answer"] = "Error: Invalid citations in response"
                valid_result["citations"] = []
    except Exception as e:
        print(f"\n❌ Error validating synthesis result: {str(e)}")
    
    return valid_result

def synthesize(question: str, documents: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Generate a concise answer with citations from the search results.
    Returns a dict with the answer and citations.
    """
    if not documents:
        return {
            "answer": "Insufficient information to provide an answer.",
            "citations": []
        }

    try:
        client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        
        formatted_docs = format_documents(documents)
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": "You are a technical writer that creates concise, well-cited answers. "
                              "You MUST return a SINGLE LINE of valid JSON with NO newlines or extra whitespace. "
                              "Do not include any other text or explanation."
                },
                {
                    "role": "user",
                    "content": SYNTHESIZE_PROMPT.format(
                        question=question,
                        documents=formatted_docs
                    )
                }
            ],
            temperature=0.1  # Lower temperature for more consistent formatting
        )
        
        content = response.choices[0].message.content
        
        # Extract and validate JSON response
        try:
            result = extract_json_from_response(content)
            return validate_synthesis_result(result, documents)
        except (json.JSONDecodeError, ValueError) as e:
            print(f"\n❌ Error processing synthesis response: {str(e)}")
            print(f"Raw response: {content}")
            return {
                "answer": "Error processing response",
                "citations": []
            }
            
    except Exception as e:
        print(f"\n❌ Error in synthesis: {str(e)}")
        return {
            "answer": "Error during synthesis",
            "citations": []
        } 