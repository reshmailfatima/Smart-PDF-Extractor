import streamlit as st
from google import genai
from google.genai import types
import os, tempfile, json, textwrap
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

@st.cache_resource
def get_genai_client():
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        st.error("Missing GOOGLE_API_KEY in .env file")
        st.stop()
    return genai.Client(api_key=api_key)

def build_system_prompt(meta: dict) -> str:
    """
    meta: dict returned by collect_user_intent()
    Returns a carefully structured prompt string for Gemini.
    """
    return textwrap.dedent(f"""
    You are a professional document analyst.  
    The user uploaded a PDF and wants the following:

    - **Primary goal** : {meta["goal"]}
    - **Preferred output style** : {meta["style"]}
    - **Specific entities to extract** : {", ".join(meta["entities"]) or "None specified"}
    - **Additional instructions** : {meta["notes"] or "None"}

    INSTRUCTIONS:
    1. Read the PDF carefully.
    2. Extract only **relevant** information that satisfies the user's goal.
    3. Present the answer in {meta["style"]} format.
    4. Use clear headings, bullet points, tables, or numbered lists where appropriate.
    6. If the requested information is **not present**, say so explicitly.
    7. Do not add external knowledge beyond what the PDF contains.

    Begin your response with a short 1-sentence summary, then proceed with the detailed answer.
    """).strip()

def collect_user_intent():
    st.markdown("### 🔍 Tell us what you need")
    
    # Use session state to persist form data
    if 'intent_submitted' not in st.session_state:
        st.session_state.intent_submitted = False
    if 'user_intent' not in st.session_state:
        st.session_state.user_intent = {}
    
    # If intent was already submitted, return the stored values
    if st.session_state.intent_submitted and st.session_state.user_intent:
        return st.session_state.user_intent
    
    with st.form("intent_form"):
        goal = st.text_area(
            "Describe the information you need in plain language",
            placeholder="e.g. 'Find all financial figures and summarize them in a table'",
            height=80,
        )

        entities = st.text_input(
            "Specific entities / fields to extract (comma-separated)",
            placeholder="e.g. Invoice Number, Total Amount, Due Date, Customer Name",
        )

        style = st.selectbox(
            "Preferred output style",
            ["Bullet list", "Numbered list", "Table", "Paragraph summary", "JSON"],
            index=0,
        )

        notes = st.text_area(
            "Any extra instructions or context?",
            height=60,
            placeholder="e.g. Convert all currencies to USD, include page references",
        )

        submitted = st.form_submit_button("Confirm & Upload", use_container_width=True)

        if submitted and goal.strip():  # Only proceed if goal is provided
            user_intent = dict(
                goal=goal.strip(),
                entities=[e.strip() for e in entities.split(",") if e.strip()],
                style=style,
                notes=notes.strip(),
            )
            st.session_state.user_intent = user_intent
            st.session_state.intent_submitted = True
            st.rerun()  # Force a rerun to update the UI
        elif submitted and not goal.strip():
            st.error("Please describe what information you need before proceeding.")
            st.stop()

    if not st.session_state.intent_submitted:
        st.stop()
    
    return st.session_state.user_intent

def process_pdf(client, uploaded_file, prompt):
    tmp_path = None
    try:
        # Create temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as f:
            f.write(uploaded_file.getbuffer())
            tmp_path = f.name

        # Upload to Gemini
        uploaded_gemini_file = client.files.upload(file=tmp_path)
        
        contents = [
            uploaded_gemini_file,
            prompt
        ]

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=contents,
            config=types.GenerateContentConfig(
                temperature=0.2,
            ),
        )
        
        return response.text
        
    except Exception as e:
        st.error(f"Error processing PDF: {str(e)}")
        return None
    finally:
        # Clean up temporary file
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except:
                pass  # Ignore cleanup errors

def display_result(result: str, meta: dict):
    st.success("✅ Extraction complete!")
    st.markdown("---")
    
    with st.expander("📋 Extracted Information", expanded=True):
        if meta["style"] == "JSON":
            try:
                parsed = json.loads(result)
                st.json(parsed)
            except json.JSONDecodeError:
                st.code(result, language="json")
        else:
            st.markdown(result)

    # Download button
    st.download_button(
        label="📥 Download as Markdown",
        data=result,
        file_name=f"extracted_{datetime.now():%Y%m%d_%H%M%S}.md",
        mime="text/markdown",
        use_container_width=True
    )
    
    # Reset button to start over
    if st.button("🔄 Extract Another PDF", use_container_width=True):
        st.session_state.intent_submitted = False
        st.session_state.user_intent = {}
        st.rerun()

def main():
    st.set_page_config(
        page_title="Smart PDF Extractor",
        page_icon="📄",
        layout="centered",
        initial_sidebar_state="collapsed",
    )

    st.title("📄 Smart PDF Extractor")
    st.markdown(
        "Upload a PDF and specify exactly what you want. "
        "This tool will extract and format the information for you."
    )

    # Initialize client
    try:
        client = get_genai_client()
    except Exception as e:
        st.error(f"Failed to initialize Gemini client: {str(e)}")
        st.stop()

    # File uploader
    uploaded_file = st.file_uploader(
        "Choose a PDF file", 
        type=["pdf"], 
        accept_multiple_files=False,
        help="Select a PDF file to analyze"
    )

    if not uploaded_file:
        st.info("👆 Please upload a PDF file to get started")
        st.stop()

    # Show file info
    st.success(f"📄 File uploaded: {uploaded_file.name} ({uploaded_file.size} bytes)")

    # Collect user intent
    try:
        meta = collect_user_intent()
    except Exception as e:
        st.error(f"Error collecting user intent: {str(e)}")
        st.stop()

    # Show current settings
    with st.expander("Current Settings", expanded=False):
        st.write("**Goal:**", meta["goal"])
        st.write("**Output Style:**", meta["style"])
        st.write("**Entities:**", ", ".join(meta["entities"]) if meta["entities"] else "None")
        st.write("**Notes:**", meta["notes"] if meta["notes"] else "None")

    # Build prompt
    prompt = build_system_prompt(meta)

    # Extract button
    if st.button("🚀 Extract Information", type="primary", use_container_width=True):
        if not uploaded_file:
            st.error("Please upload a PDF file first.")
            st.stop()
        
        if not meta["goal"]:
            st.error("Please describe what information you need.")
            st.stop()
            
        with st.spinner("🔄 Analyzing PDF... This may take a few moments."):
            try:
                result = process_pdf(client, uploaded_file, prompt)
                if result:
                    display_result(result, meta)
                else:
                    st.error("❌ Extraction failed. Please check your PDF file and try again.")
            except Exception as e:
                st.error(f"❌ An error occurred: {str(e)}")
                st.exception(e) 

if __name__ == "__main__":
    main()