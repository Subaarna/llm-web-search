import streamlit as st
from agent.main import main, run_search_cycle, synthesize
import json
import os
import time

# Set page config
st.set_page_config(
    page_title="Research Agent",
    page_icon="🔍",
    layout="wide"
)

# Add custom CSS
st.markdown("""
<style>
.citation {
    font-size: 0.8em;
    color: #666;
    padding: 0.5em;
    background-color: #f5f5f5;
    border-radius: 5px;
    margin: 0.5em 0;
}
.search-query {
    font-style: italic;
    color: #444;
    margin: 0.3em 0;
}
.process-step {
    border-left: 3px solid #f0f0f0;
    padding-left: 1em;
    margin: 1em 0;
}
.final-answer {
    border: 1px solid #e0e0e0;
    border-radius: 5px;
    padding: 1em;
    margin: 1em 0;
    background-color: #f8f8f8;
}
.stProgress .st-bo {
    background-color: #00cc00;
}
.confidence-high {
    color: #00cc00;
    font-weight: bold;
}
.confidence-medium {
    color: #ffa500;
    font-weight: bold;
}
.confidence-low {
    color: #ff4444;
    font-weight: bold;
}
.step-indicator {
    display: inline-block;
    width: 20px;
    height: 20px;
    line-height: 20px;
    text-align: center;
    border-radius: 50%;
    background-color: #e0e0e0;
    color: white;
    margin-right: 8px;
    font-size: 12px;
}
.step-complete {
    background-color: #00cc00;
}
.step-current {
    background-color: #ffa500;
    animation: pulse 2s infinite;
}
@keyframes pulse {
    0% { opacity: 1; }
    50% { opacity: 0.5; }
    100% { opacity: 1; }
}
</style>
""", unsafe_allow_html=True)

def get_confidence_class(confidence: float) -> str:
    """Return the CSS class based on confidence level."""
    if confidence >= 0.7:
        return "confidence-high"
    elif confidence >= 0.4:
        return "confidence-medium"
    else:
        return "confidence-low"

def format_step_indicator(step_number: int, current_step: int, total_steps: int) -> str:
    """Format the step indicator with the appropriate styling."""
    if step_number < current_step:
        return f'<span class="step-indicator step-complete">✓</span>'
    elif step_number == current_step:
        return f'<span class="step-indicator step-current">{step_number}</span>'
    else:
        return f'<span class="step-indicator">{step_number}</span>'

# Title and description
st.title("🔍 Research Agent")
st.markdown("""
This agent helps you research topics by:
- Generating targeted search queries
- Searching the web for relevant information
- Analyzing and synthesizing the results
- Providing concise answers with citations
""")

# Input section
question = st.text_input("Enter your research question:", key="question")

# Add a search button
if st.button("Research", type="primary"):
    if question:
        try:
            # Create containers for different sections
            progress_container = st.container()
            process_container = st.container()
            answer_container = st.container()
            
            with progress_container:
                overall_progress = st.progress(0)
                status_text = st.empty()
                confidence_text = st.empty()
                steps_text = st.empty()
            
            with process_container:
                st.subheader("📝 Research Process")
                process_placeholder = st.empty()
        
            with answer_container:
                final_placeholder = st.empty()
            
            # Initialize data collection
            all_docs = []
            iteration = 1
            total_steps = 7  # Total steps in the process
            current_step = 0
            
            def update_progress(step_name: str, step_number: int, confidence: float = 0.0):
                progress = step_number / total_steps
                overall_progress.progress(progress)
                
                # Update status with step indicator
                steps_html = "".join([
                    format_step_indicator(i + 1, step_number, total_steps)
                    for i in range(total_steps)
                ])
                steps_text.markdown(steps_html, unsafe_allow_html=True)
                
                # Update status text
                status_text.markdown(f"**Current Step {step_number}/{total_steps}:** {step_name}")
                
                # Update confidence if provided
                if confidence > 0:
                    confidence_class = get_confidence_class(confidence)
                    confidence_text.markdown(
                        f'Confidence: <span class="{confidence_class}">{confidence:.0%}</span>',
                        unsafe_allow_html=True
                    )
            
            # Run search cycles
            while iteration <= 2:  # MAX_ITER from main
                with process_placeholder.container():
                    current_iteration = st.empty()
                    current_iteration.markdown(f"### Round {iteration}")
                    
                    # Update progress - Starting new iteration
                    current_step += 1
                    update_progress(f"Starting Research Round {iteration}", current_step)
                    
                    # Generate queries
                    current_step += 1
                    update_progress("Generating Search Queries", current_step)
                    
                    docs, reflection = run_search_cycle(question, iteration, debug=True)
                    all_docs.extend(docs)
                    
                    # Show search queries with confidence
                    st.markdown(f"**Search Queries:**")
                    for query in reflection.get('new_queries', []):
                        st.markdown(f"- _{query}_")
                
                    # Update progress - Searching
                    current_step += 1
                    update_progress("Searching Web Sources", current_step)
                    
                    # Show found documents with confidence
                    if docs:
                        st.markdown(f"**Found {len(docs)} relevant documents:**")
                        for doc in docs[:3]:  # Show top 3
                            with st.expander(doc['title']):
                                st.markdown(f"[{doc['url']}]({doc['url']})")
                                st.markdown(doc['snippet'])
                    
                    # Update progress - Analyzing with confidence
                    current_step += 1
                    confidence = reflection.get('confidence', 0.0)
                    update_progress("Analyzing Results", current_step, confidence)
                    
                    # Show reflection with confidence indicator
                    st.markdown("**Reflection:**")
                    confidence_class = get_confidence_class(confidence)
                    st.markdown(
                        f'- Confidence: <span class="{confidence_class}">{confidence:.0%}</span>',
                        unsafe_allow_html=True
                    )
                    st.markdown(f"- Need more information? {'Yes' if reflection['need_more'] else 'No'}")
                    if reflection.get('reasoning'):
                        st.markdown(f"- Reasoning: {reflection['reasoning']}")
                    
                    if reflection['need_more'] and iteration < 2:
                        iteration += 1
                    else:
                        break
            
            # Update progress - Synthesizing
            current_step += 1
            update_progress("Synthesizing Final Answer", current_step, confidence)
            
            # Generate final answer
            result = synthesize(question, all_docs)
                
            # Display the answer in the required format
            final_result = {
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
            
            # Update progress - Formatting
            current_step += 1
            update_progress("Formatting Results", current_step, 1.0)
            
            with final_placeholder.container():
                st.subheader("📊 Final Answer")
                
                # Show formatted answer
                st.markdown(f"**Answer:**")
                st.markdown(final_result["answer"])
                
                # Show citations
                if final_result["citations"]:
                    st.markdown("**Sources:**")
                    for citation in final_result["citations"]:
                        st.markdown(
                            f"""<div class='citation'>
                        [{citation['id']}] <a href="{citation['url']}" target="_blank">{citation['title']}</a>
                            </div>""",
                            unsafe_allow_html=True
                        )
                
                # Show raw JSON
                with st.expander("View JSON Output"):
                    st.code(json.dumps(final_result, indent=2, ensure_ascii=False), language="json")
            
            # Update progress - Complete
            current_step += 1
            update_progress("Research Complete! ✨", current_step, 1.0)
                
        except Exception as e:
            st.error("An error occurred while processing your question.")
            st.error(str(e))
    else:
        st.warning("Please enter a research question.")

# Add API key configuration section
with st.sidebar:
    st.header("⚙️ Configuration")
    
    # API Keys
    groq_key = st.text_input("GROQ API Key", type="password")
    tavily_key = st.text_input("Tavily API Key", type="password")
    
    if groq_key:
        st.session_state["GROQ_API_KEY"] = groq_key
        os.environ["GROQ_API_KEY"] = groq_key
    if tavily_key:
        st.session_state["TAVILY_API_KEY"] = tavily_key
        os.environ["TAVILY_API_KEY"] = tavily_key
        
    # Show API key status
    st.markdown("### API Key Status")
    groq_status = "✅" if (os.getenv("GROQ_API_KEY") or st.session_state.get("GROQ_API_KEY")) else "❌"
    tavily_status = "✅" if (os.getenv("TAVILY_API_KEY") or st.session_state.get("TAVILY_API_KEY")) else "❌"
    st.markdown(f"- GROQ API: {groq_status}")
    st.markdown(f"- Tavily API: {tavily_status}")
    
    # Add some helpful information
    st.markdown("""
    ### 📝 Notes
    - The agent will generate multiple search queries
    - Results are limited to 80 words
    - All sources are cited with links
    """) 