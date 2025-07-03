# src/agent/main.py

import sys
import json
from typing import List, Dict, Any
from agent.nodes.generate_queries import generate_queries
from agent.tools.web_search import search_all
from agent.nodes.reflect import reflect
from agent.nodes.synthesize import synthesize

# Maximum number of search-reflect cycles as per the requirements
MAX_ITER = 2  

#function to run one cycle of search and reflection
def run_search_cycle(question: str, iteration: int = 1, debug: bool = False) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Run one cycle of search and reflection."""
    # Generate search queries
    queries = generate_queries(question)
    if not queries:
        if debug:
            print("Failed to generate search queries", file=sys.stderr)
        return [], {
            "need_more": True,
            "new_queries": [question]
        }
    
    if debug:
        print(f"Search queries (Round {iteration}): {', '.join(queries)}", file=sys.stderr)

    # Perform web search using the search_all function from the web_search.py file
    docs = search_all(queries)
    if not docs:
        if debug:
            print("No search results found", file=sys.stderr)
        return [], {
            "need_more": True,
            "new_queries": queries[:1]
        }
        
    if debug:
        print(f"Found {len(docs)} relevant documents", file=sys.stderr)

    # Reflect on the search results
    reflection = reflect(question, docs)
    
    return docs, reflection

#main function that processes the question and returns the final answer with citations
def main(question: str, debug: bool = False) -> Dict[str, Any]:
    """
    Main function that processes the question and returns the final answer with citations.
    Returns a JSON object with the answer and citations.
    """
    all_docs = []
    iteration = 1
    #loop through the search cycles
    while iteration <= MAX_ITER:
        docs, reflection = run_search_cycle(question, iteration, debug)
        all_docs.extend(docs)
        #if the reflection needs more information, increment the iteration
        if reflection['need_more'] and iteration < MAX_ITER:
            iteration += 1
        else:
            break
    
    # Generate final answer
    result = synthesize(question, all_docs)
    
    # Ensure the output matches the required format
    return {
        "answer": result["answer"],
        "citations": [
            {
                "id": citation["id"],
                "title": citation["title"],
                "url": citation["url"]
            }
            for citation in result["citations"]
        ]
    }

if __name__ == "__main__":
    # Check for debug flag
    debug_mode = "--debug" in sys.argv
    if debug_mode:
        sys.argv.remove("--debug")

    #check if the question is provided
    if len(sys.argv) < 2:
        print("Usage: python main.py [--debug] '<your question>'", file=sys.stderr)
        sys.exit(1)

    #try to process the question and return the result
    try:
        result = main(sys.argv[1], debug=debug_mode)
        # Output clean, minimal JSON
        print(json.dumps(result, ensure_ascii=False, indent=2))

    except Exception as e:
        error_json = {
            "answer": "An error occurred while processing your question.",
            "citations": []
        }
        #print the error message and exit the program
        print(json.dumps(error_json, ensure_ascii=False, indent=2))
        if debug_mode:
            print(f"Error: {str(e)}", file=sys.stderr)
        sys.exit(1)
