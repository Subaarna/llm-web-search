import pytest
from unittest.mock import patch, MagicMock
from agent.nodes.reflect import reflect, format_documents, identify_slots

# Sample test data
SAMPLE_DOCS = [
    {
        "title": "World Cup 2022 Final Score",
        "url": "http://test1.com",
        "snippet": "Argentina won the 2022 World Cup final with a score of 4-2 on penalties after a 3-3 draw with France on December 18, 2022."
    },
    {
        "title": "World Cup Final Analysis",
        "url": "http://test2.com",
        "snippet": "In regular time, Messi scored twice for Argentina while Mbappe scored a hat-trick for France."
    }
]

def test_format_documents():
    """Test document formatting function"""
    formatted = format_documents(SAMPLE_DOCS)
    assert "[1]" in formatted
    assert "[2]" in formatted
    assert "World Cup 2022 Final Score" in formatted
    assert "World Cup Final Analysis" in formatted
    assert "http://test1.com" in formatted
    assert "http://test2.com" in formatted

@patch('agent.nodes.reflect.Groq')
def test_identify_slots(mock_groq):
    """Test slot identification"""
    # Setup mock
    mock_client = MagicMock()
    mock_groq.return_value = mock_client
    mock_completion = MagicMock()
    mock_completion.choices = [
        MagicMock(message=MagicMock(content='{"slots":["argentina_score","france_score"],"descriptions":["Goals scored by Argentina","Goals scored by France"]}'))
    ]
    mock_client.chat.completions.create.return_value = mock_completion
    
    # Test
    slots, descriptions = identify_slots("What was the score of the World Cup final?", mock_client)
    
    # Verify
    assert "argentina_score" in slots
    assert "france_score" in slots
    assert len(descriptions) == len(slots)
    assert any("Argentina" in desc for desc in descriptions)
    assert any("France" in desc for desc in descriptions)

@patch('agent.nodes.reflect.Groq')
def test_slot_aware_reflection_complete(mock_groq):
    """Test reflection with all slots filled"""
    # Setup mock for slot identification
    mock_client = MagicMock()
    mock_groq.return_value = mock_client
    
    # First call for slot identification
    mock_completion1 = MagicMock()
    mock_completion1.choices = [
        MagicMock(message=MagicMock(content='{"slots":["argentina_score","france_score"],"descriptions":["Goals scored by Argentina","Goals scored by France"]}'))
    ]
    
    # Second call for reflection
    mock_completion2 = MagicMock()
    mock_completion2.choices = [
        MagicMock(message=MagicMock(content='''
        {
            "slots": ["argentina_score","france_score"],
            "filled": [true,true],
            "evidence": {
                "argentina_score": "Argentina won with a score of 4-2",
                "france_score": "France scored 2 goals"
            },
            "need_more": false,
            "confidence": 0.9,
            "reasoning": "Both scores found",
            "new_queries": []
        }
        '''))
    ]
    
    mock_client.chat.completions.create.side_effect = [mock_completion1, mock_completion2]
    
    # Test
    result = reflect("What was the score of the World Cup final?", SAMPLE_DOCS)
    
    # Verify
    assert result["slots"] == ["argentina_score", "france_score"]
    assert all(result["filled"])
    assert len(result["evidence"]) == 2
    assert not result["need_more"]
    assert result["confidence"] > 0.5

@patch('agent.nodes.reflect.Groq')
def test_slot_aware_reflection_incomplete(mock_groq):
    """Test reflection with missing slots"""
    # Setup mock
    mock_client = MagicMock()
    mock_groq.return_value = mock_client
    
    # First call for slot identification
    mock_completion1 = MagicMock()
    mock_completion1.choices = [
        MagicMock(message=MagicMock(content='{"slots":["argentina_score","france_score","match_date"],"descriptions":["Goals by Argentina","Goals by France","Date of match"]}'))
    ]
    
    # Second call for reflection
    mock_completion2 = MagicMock()
    mock_completion2.choices = [
        MagicMock(message=MagicMock(content='''
        {
            "slots": ["argentina_score","france_score","match_date"],
            "filled": [true,false,true],
            "evidence": {
                "argentina_score": "Argentina scored 3 goals",
                "match_date": "December 18, 2022"
            },
            "need_more": true,
            "confidence": 0.5,
            "reasoning": "France's score not found",
            "new_queries": ["How many goals did France score in World Cup 2022 final"]
        }
        '''))
    ]
    
    mock_client.chat.completions.create.side_effect = [mock_completion1, mock_completion2]
    
    # Test
    result = reflect("What was the score of the World Cup final?", SAMPLE_DOCS)
    
    # Verify
    assert len(result["slots"]) == 3
    assert not all(result["filled"])
    assert len(result["evidence"]) == 2
    assert result["need_more"]
    assert len(result["new_queries"]) > 0
    assert any("France" in query for query in result["new_queries"])

@patch('agent.nodes.reflect.Groq')
def test_slot_aware_reflection_error_handling(mock_groq):
    """Test error handling in slot-aware reflection"""
    # Setup mock to raise an exception
    mock_groq.return_value.chat.completions.create.side_effect = Exception("API Error")
    
    # Test
    result = reflect("test question", SAMPLE_DOCS)
    
    # Verify error handling
    assert "slots" in result
    assert "filled" in result
    assert "evidence" in result
    assert result["need_more"]
    assert result["confidence"] == 0.0
    assert "Error" in result["reasoning"]
    assert len(result["new_queries"]) > 0

def test_reflection_no_documents():
    """Test reflection with no documents"""
    result = reflect("test question", [])
    
    # Verify
    assert result["slots"] == ["answer"]
    assert not any(result["filled"])
    assert not result["evidence"]
    assert result["need_more"]
    assert "No search results" in result["reasoning"]

@pytest.mark.parametrize("mock_response,expected", [
    (
        # Mock response where more info is needed
        {
            "need_more": True,
            "reasoning": "Need more technical details",
            "new_queries": ["additional query 1", "additional query 2"]
        },
        # Expected output
        {
            "need_more": True,
            "reasoning": "Need more technical details",
            "new_queries": ["additional query 1", "additional query 2"]
        }
    ),
    (
        # Mock response where enough info is present
        {
            "need_more": False,
            "reasoning": "Sufficient information available"
        },
        # Expected output
        {
            "need_more": False,
            "reasoning": "Sufficient information available"
        }
    )
])
@patch('agent.nodes.reflect.Groq')
def test_reflect_with_documents(mock_groq, mock_response, expected):
    """Test reflection with documents"""
    # Setup mock
    mock_client = MagicMock()
    mock_groq.return_value = mock_client
    mock_completion = MagicMock()
    mock_completion.choices = [
        MagicMock(message=MagicMock(content=str(mock_response)))
    ]
    mock_client.chat.completions.create.return_value = mock_completion

    # Test
    result = reflect("test question", SAMPLE_DOCS)
    
    # Verify
    assert result["need_more"] == expected["need_more"]
    assert result["reasoning"] == expected["reasoning"]
    if expected["need_more"]:
        assert "new_queries" in result
        assert len(result["new_queries"]) > 0

@patch('agent.nodes.reflect.Groq')
def test_reflect_api_error(mock_groq):
    """Test handling of API errors"""
    # Setup mock to raise an exception
    mock_groq.return_value.chat.completions.create.side_effect = Exception("API Error")
    
    # Test
    result = reflect("test question", SAMPLE_DOCS)
    
    # Verify error handling
    assert result["need_more"] == True
    assert "Error" in result["reasoning"]
    assert len(result["new_queries"]) > 0 