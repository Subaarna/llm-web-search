#!/usr/bin/env python3

import sys
import json
from agent.main import main

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python run.py '<your question>'", file=sys.stderr)
        sys.exit(1)
    
    try:
        # Run the agent and get result
        result = main(sys.argv[1])
        
        # Format and print JSON output
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as e:
        # Return error in the same JSON format
        error_result = {
            "answer": "An error occurred while processing your question.",
            "citations": []
        }
        print(json.dumps(error_result, ensure_ascii=False, indent=2))
        print(f"Error: {str(e)}", file=sys.stderr)
        sys.exit(1) 