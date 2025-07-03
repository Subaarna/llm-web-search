import os
import requests

#retrieving our api key from the environment variables
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
TAVILY_ENDPOINT = "https://api.tavily.com/search"

# Mock results for testing when API key is not available
MOCK_RESULTS = [
    {
        "title": "Mock Search Result 1",
        "url": "https://example.com/mock1",
        "snippet": "This is a mock search result for testing purposes."
    },
    {
        "title": "Mock Search Result 2",
        "url": "https://example.com/mock2",
        "snippet": "Another mock search result for testing."
    }
]

# function to search the web using tavily api
def tavily_search(query: str) -> list[dict]:
    if not TAVILY_API_KEY:
        print(f"[Tavily] No API key found, using mock results for '{query}'")
        return MOCK_RESULTS
        
#setting up the headers and json payload
    headers = {"Authorization": f"Bearer {TAVILY_API_KEY}"}
    json_payload = {
        "query": query,
        "search_depth": "basic", 
        "include_answer": False
    }
#try to make the request and return the results
    try:
        response = requests.post(TAVILY_ENDPOINT, headers=headers, json=json_payload, timeout=10)
        response.raise_for_status()
        results = response.json().get("results", [])
        return [
            {
                "title": item["title"],
                "url": item["url"],
                "snippet": item["content"]
            }
            for item in results
        ]
    except requests.RequestException as e:
        print(f"[Tavily] Error querying Tavily for '{query}': {e}")
        return []

#function to search the web using multiple queries stored in a list and return the results
def search_all(queries: list[str]) -> list[dict]:
    seen_urls = set()
    all_results = []
    #loop through the queries and search the web
    for query in queries:
        results = tavily_search(query)
        for result in results:
            if result["url"] not in seen_urls:
                seen_urls.add(result["url"])
                #add the result to the list of results
                all_results.append(result)
    
    return all_results
