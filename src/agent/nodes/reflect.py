import os
import json
import re
from typing import List, Dict, Any, Tuple
from groq import Groq

SLOT_IDENTIFICATION_PROMPT = """
Analyze this question and identify the key information slots that need to be filled for a complete answer.
A slot is a specific piece of information that must be found to answer the question fully.

Question: {question}

Return a SINGLE LINE of valid JSON with NO newlines. Format:
{{"slots":["slot1","slot2"],"descriptions":["what slot1 means","what slot2 means"]}}

Example 1:
Question: "What was the score of the 2022 World Cup final?"
{{"slots":["argentina_score","france_score","match_date"],"descriptions":["Number of goals scored by Argentina","Number of goals scored by France","Date of the final match"]}}

Example 2:
Question: "Who is the current CEO of Apple and when did they start?"
{{"slots":["ceo_name","start_date"],"descriptions":["Name of Apple's current CEO","When they started as CEO"]}}
"""

REFLECT_PROMPT = """
Analyze these search results to determine if we have enough information to answer the question.
For each required slot, find evidence in the search results that fills it.

Question: {question}

Required Slots:
{slots_info}

Search Results:
{documents}

IMPORTANT: Return a SINGLE LINE of valid JSON with NO newlines or extra whitespace. Format:
{{
  "slots": ["slot1", "slot2"],
  "filled": [true/false, true/false],
  "evidence": {{"slot1": "exact text from docs that fills slot1", "slot2": "exact text from docs that fills slot2"}},
  "need_more": true/false,
  "confidence": 0.0-1.0,
  "reasoning": "Brief explanation of what's missing or conflicting",
  "new_queries": ["targeted query for missing slot"]
}}
"""

def format_slots_info(slots: List[str], descriptions: List[str]) -> str:
    """Format slots and their descriptions for the prompt."""
    return "\n".join(f"- {slot}: {desc}" for slot, desc in zip(slots, descriptions))

def format_documents(docs: List[Dict[str, Any]]) -> str:
    """Format documents into a string for the prompt."""
    formatted_docs = []
    for i, doc in enumerate(docs, 1):
        formatted_docs.append(
            f"[{i}] Title: {doc['title']}\n"
            f"URL: {doc['url']}\n"
            f"Content: {doc['snippet']}\n"
        )
    return "\n".join(formatted_docs)

def extract_json_from_response(content: str) -> Dict[str, Any]:
    """Extract and validate JSON from the response."""
    # Remove any non-JSON content
    content = content.strip()
    
    # Find anything that looks like JSON with proper nesting
    json_pattern = r'\{(?:[^{}]|(?:\{(?:[^{}]|(?:\{[^{}]*\})*)*\}))*\}'
    matches = re.finditer(json_pattern, content)
    last_match = None
    for match in matches:
        last_match = match
    
    if not last_match:
        raise ValueError(f"No JSON object found in response: {content}")
    
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

def identify_slots(question: str, client: Groq) -> Tuple[List[str], List[str]]:
    """Identify required information slots for the question."""
    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": "You are an analytical assistant that identifies required information slots. "
                              "Return ONLY a SINGLE LINE of valid JSON with NO newlines or extra whitespace."
                },
                {
                    "role": "user",
                    "content": SLOT_IDENTIFICATION_PROMPT.format(question=question)
                }
            ],
            temperature=0.1
        )
        
        result = extract_json_from_response(response.choices[0].message.content)
        return result.get("slots", []), result.get("descriptions", [])
    except Exception as e:
        print(f"\n❌ Error identifying slots: {str(e)}")
        # Return a basic slot as fallback
        return ["answer"], ["The complete answer to the question"]

def validate_reflection_result(result: Dict[str, Any], slots: List[str], question: str) -> Dict[str, Any]:
    """Validate and normalize reflection result."""
    # Create a default valid result
    valid_result = {
        "slots": slots,
        "filled": [False] * len(slots),
        "evidence": {},
        "need_more": True,
        "confidence": 0.0,
        "reasoning": "",
        "new_queries": [question]
    }
    
    try:
        # Validate slots match
        if result.get("slots") == slots:
            # Validate filled status
            if isinstance(result.get("filled"), list) and len(result["filled"]) == len(slots):
                valid_result["filled"] = [bool(x) for x in result["filled"]]
            
            # Validate evidence
            if isinstance(result.get("evidence"), dict):
                valid_result["evidence"] = {
                    slot: str(evidence)
                    for slot, evidence in result["evidence"].items()
                    if slot in slots and isinstance(evidence, str)
                }
            
            # Validate need_more (must be True if any slot is unfilled)
        if isinstance(result.get("need_more"), bool):
                valid_result["need_more"] = result["need_more"] or not all(valid_result["filled"])
        
        # Validate confidence
        if isinstance(result.get("confidence"), (int, float)):
                valid_result["confidence"] = max(0.0, min(1.0, float(result["confidence"])))
        
        # Validate reasoning
        if isinstance(result.get("reasoning"), str) and result["reasoning"]:
            valid_result["reasoning"] = result["reasoning"]
        
        # Validate new_queries
        if isinstance(result.get("new_queries"), list):
            valid_queries = [q for q in result["new_queries"] if isinstance(q, str) and q]
            if valid_queries:
                valid_result["new_queries"] = valid_queries
    except Exception as e:
        print(f"\n❌ Error validating reflection result: {str(e)}")
    
    return valid_result

def reflect(question: str, documents: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Analyze search results and determine if more information is needed.
    Uses slot-aware reflection to track specific pieces of required information.
    Returns a dict with reflection results including slot status.
    """
    if not documents:
        return {
            "slots": ["answer"],
            "filled": [False],
            "evidence": {},
            "need_more": True,
            "confidence": 0.0,
            "reasoning": "No search results to analyze",
            "new_queries": [question]
        }

    try:
        client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        
        # First, identify required slots
        slots, descriptions = identify_slots(question, client)
        slots_info = format_slots_info(slots, descriptions)
        
        # Then analyze documents for slot filling
        formatted_docs = format_documents(documents)
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": "You are an analytical assistant that evaluates search results. "
                              "You MUST return a SINGLE LINE of valid JSON with NO newlines or extra whitespace. "
                              "Do not include any other text or explanation."
                },
                {
                    "role": "user",
                    "content": REFLECT_PROMPT.format(
                        question=question,
                        slots_info=slots_info,
                        documents=formatted_docs
                    )
                }
            ],
            temperature=0.1
        )
        
        content = response.choices[0].message.content
        
        # Extract and validate JSON response
        try:
            result = extract_json_from_response(content)
            return validate_reflection_result(result, slots, question)
        except (json.JSONDecodeError, ValueError) as e:
            print(f"\n❌ Error processing reflection response: {str(e)}")
            print(f"Raw response: {content}")
            return {
                "slots": slots,
                "filled": [False] * len(slots),
                "evidence": {},
                "need_more": True,
                "confidence": 0.0,
                "reasoning": "Error processing response",
                "new_queries": [question]
            }
            
    except Exception as e:
        print(f"\n❌ Error in reflection: {str(e)}")
        return {
            "slots": ["answer"],
            "filled": [False],
            "evidence": {},
            "need_more": True,
            "confidence": 0.0,
            "reasoning": "Error during reflection",
            "new_queries": [question]
        }
