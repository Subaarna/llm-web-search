import pytest
from unittest.mock import patch, MagicMock
import requests
from agent.main import main, run_search_cycle
from agent.tools.web_search import search_all
from agent.nodes.generate_queries import generate_queries
from agent.nodes.synthesize import synthesize

# Sample test data
SAMPLE_DOCS = [
    {
        "title": "HPA vs KEDA in Kubernetes",
        "url": "https://example.com/hpa-vs-keda",
        "snippet": "HPA is for CPU/memory scaling, KEDA for event-driven scaling."
    },
    {
        "title": "Kubernetes Autoscaling Guide",
        "url": "https://example.com/k8s-autoscaling",
        "snippet": "Comparing different autoscaling options in Kubernetes."
    }
]

@pytest.fixture
def mock_groq():
    with patch('agent.nodes.reflect.Groq') as mock:
        # Mock successful reflection response
        mock_client = MagicMock()
        mock_completion = MagicMock()
        mock_completion.choices = [
            MagicMock(message=MagicMock(content='{"need_more":false,"confidence":0.9,"reasoning":"Good info found","new_queries":[]}'))
        ]
        mock_client.chat.completions.create.return_value = mock_completion
        mock.return_value = mock_client
        yield mock

@pytest.fixture
def mock_tavily():
    with patch('agent.tools.web_search.requests.post') as mock:
        mock_response = MagicMock()
        mock_response.json.return_value = {"results": [
            {"title": doc["title"], "url": doc["url"], "content": doc["snippet"]}
            for doc in SAMPLE_DOCS
        ]}
        mock.return_value = mock_response
        yield mock

def test_happy_path(mock_groq, mock_tavily):
    """Test successful end-to-end flow with good results"""
    # Mock synthesis response
    with patch('agent.nodes.synthesize.Groq') as mock_synth:
        mock_client = MagicMock()
        mock_completion = MagicMock()
        mock_completion.choices = [
            MagicMock(message=MagicMock(content='{"answer":"HPA handles CPU/memory scaling while KEDA enables event-driven scaling [1][2]","citations":[{"id":1,"title":"HPA vs KEDA in Kubernetes","url":"https://example.com/hpa-vs-keda"}]}'))
        ]
        mock_client.chat.completions.create.return_value = mock_completion
        mock_synth.return_value = mock_client
        
        # Run test
        result = main("Compare Kubernetes HPA and KEDA")
        
        # Verify
        assert not result.get("error")
        assert "HPA" in result["answer"]
        assert "KEDA" in result["answer"]
        assert len(result["citations"]) > 0

def test_no_results(mock_groq):
    """Test handling of no search results"""
    with patch('agent.tools.web_search.requests.post') as mock_tavily:
        # Mock empty search results
        mock_response = MagicMock()
        mock_response.json.return_value = {"results": []}
        mock_tavily.return_value = mock_response
        
        # Run test
        result = main("Compare Kubernetes HPA and KEDA")
        
        # Verify
        assert "Insufficient information" in result["answer"]
        assert len(result["citations"]) == 0

def test_rate_limit_error(mock_groq):
    """Test handling of HTTP 429 rate limit error"""
    with patch('agent.tools.web_search.requests.post') as mock_tavily:
        # Mock rate limit error
        mock_tavily.side_effect = requests.exceptions.HTTPError(
            response=MagicMock(status_code=429)
        )
        
        # Run test
        result = main("Compare Kubernetes HPA and KEDA")
        
        # Verify
        assert "Error" in result["answer"]
        assert len(result["citations"]) == 0

def test_timeout_error(mock_groq):
    """Test handling of web search timeout"""
    with patch('agent.tools.web_search.requests.post') as mock_tavily:
        # Mock timeout
        mock_tavily.side_effect = requests.exceptions.Timeout("Request timed out")
        
        # Run test
        result = main("Compare Kubernetes HPA and KEDA")
        
        # Verify
        assert "Error" in result["answer"]
        assert len(result["citations"]) == 0

def test_two_round_search(mock_tavily):
    """Test two-round search when first round needs more info"""
    # Mock web search results
    mock_response = MagicMock()
    mock_response.json.return_value = {"results": [
        {"title": "Test Doc", "url": "https://example.com", "content": "Test content"}
    ]}
    mock_tavily.return_value = mock_response

    with patch('agent.nodes.reflect.Groq') as mock_groq:
        # Mock first reflection needing more info
        mock_client1 = MagicMock()
        mock_completion1 = MagicMock()
        mock_completion1.choices = [
            MagicMock(message=MagicMock(content='{"need_more":true,"confidence":0.5,"reasoning":"Need more details","new_queries":["additional query"],"slots":["info"],"filled":[false],"evidence":{}}'))
        ]
        # Mock second reflection being satisfied
        mock_completion2 = MagicMock()
        mock_completion2.choices = [
            MagicMock(message=MagicMock(content='{"need_more":false,"confidence":0.9,"reasoning":"Got all needed info","new_queries":[],"slots":["info"],"filled":[true],"evidence":{"info":"found info"}}'))
        ]
        mock_client1.chat.completions.create.side_effect = [mock_completion1, mock_completion2]
        mock_groq.return_value = mock_client1
        
        # Mock synthesis
        with patch('agent.nodes.synthesize.Groq') as mock_synth:
            mock_client2 = MagicMock()
            mock_completion3 = MagicMock()
            mock_completion3.choices = [
                MagicMock(message=MagicMock(content='{"answer":"Final answer after two rounds [1]","citations":[{"id":1,"title":"Test Doc","url":"https://example.com"}]}'))
            ]
            mock_client2.chat.completions.create.return_value = mock_completion3
            mock_synth.return_value = mock_client2
            
            # Run test
            result = main("Compare Kubernetes HPA and KEDA")
            
            # Verify
            assert not result.get("error")
            assert "Final answer" in result["answer"]
            assert len(result["citations"]) > 0
            # Verify two rounds occurred
            assert mock_client1.chat.completions.create.call_count == 2

# New test cases for GenerateQueries
def test_generate_queries_count():
    """Test that generate_queries returns 3-5 queries"""
    with patch('agent.nodes.generate_queries.Groq') as mock_groq:
        mock_client = MagicMock()
        mock_completion = MagicMock()
        mock_completion.choices = [
            MagicMock(message=MagicMock(content='["query1", "query2", "query3", "query4"]'))
        ]
        mock_client.chat.completions.create.return_value = mock_completion
        mock_groq.return_value = mock_client
        
        queries = generate_queries("Compare Kubernetes HPA and KEDA")
        assert 3 <= len(queries) <= 5

def test_generate_queries_error():
    """Test error handling in generate_queries"""
    with patch('agent.nodes.generate_queries.Groq') as mock_groq:
        mock_groq.return_value.chat.completions.create.side_effect = Exception("API Error")
        queries = generate_queries("test question")
        assert len(queries) == 0

# New test cases for WebSearchTool
def test_web_search_concurrent():
    """Test concurrent execution of multiple queries"""
    with patch('agent.tools.web_search.requests.post') as mock_post:
        mock_response = MagicMock()
        mock_response.json.return_value = {"results": [
            {"title": "Doc 1", "url": "url1", "content": "content1"},
            {"title": "Doc 2", "url": "url2", "content": "content2"}
        ]}
        mock_post.return_value = mock_response
        
        results = search_all(["query1", "query2", "query3"])
        assert len(results) > 0
        # Verify each query was called
        assert mock_post.call_count >= 3

def test_web_search_deduplication():
    """Test deduplication of search results"""
    with patch('agent.tools.web_search.requests.post') as mock_post:
        # Return same document for different queries
        mock_response = MagicMock()
        mock_response.json.return_value = {"results": [
            {"title": "Same Doc", "url": "same_url", "content": "same content"},
            {"title": "Same Doc", "url": "same_url", "content": "same content"}
        ]}
        mock_post.return_value = mock_response
        
        results = search_all(["query1", "query2"])
        # Should deduplicate identical results
        assert len(results) == 1

def test_web_search_mock_fallback():
    """Test fallback to mock search when API key is missing"""
    with patch('agent.tools.web_search.TAVILY_API_KEY', None):  # Simulate missing API key
        with patch('agent.tools.web_search.requests.post') as mock_post:
            mock_post.side_effect = Exception("Should not be called")
            
            results = search_all(["test query"])
            # Should return mock results without calling API
            assert len(results) > 0
            assert mock_post.call_count == 0

# New test cases for Synthesize
def test_synthesize_word_limit():
    """Test that synthesized answer respects 80-word limit"""
    with patch('agent.nodes.synthesize.Groq') as mock_groq:
        mock_client = MagicMock()
        mock_completion = MagicMock()
        # Create a response with exactly 81 words
        long_answer = " ".join(["word"] * 81)
        mock_completion.choices = [
            MagicMock(message=MagicMock(content=f'{{"answer":"{long_answer}","citations":[{{"id":1,"title":"Test","url":"test.com"}}]}}'))
        ]
        mock_client.chat.completions.create.return_value = mock_completion
        mock_groq.return_value = mock_client
        
        result = synthesize("test question", SAMPLE_DOCS)
        # Count words in the answer
        word_count = len(result["answer"].split())
        assert word_count <= 80

def test_synthesize_citation_format():
    """Test that citations are properly formatted"""
    with patch('agent.nodes.synthesize.Groq') as mock_groq:
        mock_client = MagicMock()
        mock_completion = MagicMock()
        mock_completion.choices = [
            MagicMock(message=MagicMock(content='{"answer":"Test answer [1][2]","citations":[{"id":1,"title":"First","url":"url1"},{"id":2,"title":"Second","url":"url2"}]}'))
        ]
        mock_client.chat.completions.create.return_value = mock_completion
        mock_groq.return_value = mock_client
        
        result = synthesize("test question", SAMPLE_DOCS)
        # Check citation format in answer
        assert "[1]" in result["answer"]
        assert "[2]" in result["answer"]
        # Check citation objects
        assert all(isinstance(c["id"], int) for c in result["citations"])
        assert all("title" in c and "url" in c for c in result["citations"])

def test_synthesize_json_structure():
    """Test that synthesize returns valid JSON structure"""
    with patch('agent.nodes.synthesize.Groq') as mock_groq:
        mock_client = MagicMock()
        mock_completion = MagicMock()
        mock_completion.choices = [
            MagicMock(message=MagicMock(content='{"answer":"Test","citations":[{"id":1,"title":"Test","url":"test.com"}]}'))
        ]
        mock_client.chat.completions.create.return_value = mock_completion
        mock_groq.return_value = mock_client
        
        result = synthesize("test question", SAMPLE_DOCS)
        # Check required fields
        assert "answer" in result
        assert "citations" in result
        assert isinstance(result["citations"], list)
        # Check citation structure
        for citation in result["citations"]:
            assert all(key in citation for key in ["id", "title", "url"]) 