import streamlit as st
import os
import io
from PyPDF2 import PdfReader
from docx import Document
from main import run_qa_pipeline
import time

# ==========================================
# UI CONFIGURATION & STYLING
# ==========================================
st.set_page_config(page_title="QA Agent", page_icon="🤖", layout="wide")

# Custom CSS for Solid Pink and Black theme (No glow)
st.markdown("""
    <style>
    /* Main background */
    .stApp {
        background-color: #1a1a1a;
        color: #ffe6f2;
    }
    
    /* Headers */
    h1, h2, h3 {
        color: #ff66b2 !important;
        font-family: 'Helvetica Neue', sans-serif;
    }
    
    /* Solid, bright pink title (no glow) */
    .solid-title {
        text-align: center;
        font-size: 4em;
        font-weight: bold;
        color: #ff3399; /* Solid Pink */
        margin-bottom: 30px;
    }
    
    /* Textarea */
    .stTextArea textarea {
        background-color: #262626 !important;
        color: #ff99cc !important;
        border: 2px solid #ff3399 !important;
        border-radius: 10px;
        font-size: 1.1em;
    }
    
    /* Buttons */
    .stButton>button {
        background-color: #ff3399; /* Solid Pink */
        color: white;
        border: none;
        border-radius: 25px;
        padding: 10px 24px;
        font-size: 1.2em;
        font-weight: bold;
    }
    .stButton>button:hover {
        background-color: #ff1a8c;
    }
    
    /* Expander / Status Boxes */
    .streamlit-expanderHeader {
        background-color: #331a26 !important;
        color: #ff99cc !important;
        border: 1px solid #ff3399 !important;
    }
    
    /* Code blocks / outputs */
    pre {
        background-color: #000000 !important;
        border: 1px solid #ff3399 !important;
        color: #ffb3d9 !important;
    }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# FILE-BASED STATE MANAGEMENT
# ==========================================
STORY_FILE = "saved_user_story.txt"

def load_saved_story():
    if os.path.exists(STORY_FILE):
        with open(STORY_FILE, "r") as f:
            return f.read()
    return ""

def save_story(story_text):
    with open(STORY_FILE, "w") as f:
        f.write(story_text)

# Initialize session state from file if not already set
if "user_story_input" not in st.session_state:
    st.session_state.user_story_input = load_saved_story()

# Update the file whenever the text area changes
def on_story_change():
    save_story(st.session_state.user_story_input)

# ==========================================
# DOCUMENT EXTRACTION HELPERS
# ==========================================
def extract_text_from_pdf(file) -> str:
    reader = PdfReader(file)
    text = ""
    for page in reader.pages:
        text += page.extract_text() + "\n"
    return text

def extract_text_from_docx(file) -> str:
    doc = Document(file)
    text = ""
    for para in doc.paragraphs:
        text += para.text + "\n"
    return text

# ==========================================
# PAGE CONTENT
# ==========================================
st.markdown('<div class="solid-title">🤖 QA Agent</div>', unsafe_allow_html=True)
st.markdown("<h3 style='text-align: center;'>AI-Powered Automated Testing Pipeline</h3>", unsafe_allow_html=True)
st.write("---")

# Document Upload Section
st.markdown("#### 📄 Upload PRD Document (Optional)")
uploaded_file = st.file_uploader("Upload a .pdf or .docx file to automatically extract the User Story", type=["pdf", "docx"])

if uploaded_file is not None:
    # Check if we've already processed this exact file to avoid infinite loops
    if st.session_state.get("last_uploaded_file") != uploaded_file.name:
        with st.spinner("Extracting text from document..."):
            extracted_text = ""
            try:
                if uploaded_file.name.endswith(".pdf"):
                    extracted_text = extract_text_from_pdf(uploaded_file)
                elif uploaded_file.name.endswith(".docx"):
                    extracted_text = extract_text_from_docx(uploaded_file)
                
                if extracted_text.strip():
                    st.session_state.user_story_input = extracted_text
                    save_story(extracted_text)
                    st.session_state["last_uploaded_file"] = uploaded_file.name
                    st.success("Successfully extracted text from document!")
                    st.rerun() # Force a rerun to update the text area
                else:
                    st.warning("Could not extract any text from the document.")
            except Exception as e:
                st.error(f"Error reading document: {e}")

# User Input Text Area
user_story = st.text_area(
    "Enter User Story / PRD Requirements:",
    key="user_story_input",
    on_change=on_story_change,
    height=200,
    placeholder="e.g., Go to https://app.mazu.in/login, enter email test@test.com, password pass123 and login. Verify successful redirection to dashboard."
)

if st.button("🚀 Run QA Pipeline"):
    # Always save the latest story right before running, just in case
    save_story(user_story)

    if not user_story.strip():
        st.error("Please enter a user story first!")
    else:
        # Containers to hold the output dynamically
        st.markdown("### 🏃 Execution Status")
        status_text = st.empty()
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.markdown("#### 📝 1. Test Cases")
            test_cases_box = st.empty()
        with col2:
            st.markdown("#### ⚙️ 2. Execution Log")
            execution_box = st.empty()
        with col3:
            st.markdown("#### 🩹 3. Test Healer")
            # We'll use a placeholder that we can append to for multiple heal attempts
            healer_box = st.empty()
        with col4:
            st.markdown("#### 📊 4. Final Report")
            report_box = st.empty()

        # Custom callback function to update UI from the backend main.py
        healer_messages = []
        
        def ui_callback(message, step_type):
            if step_type == "status":
                status_text.info(f"🔄 **Current Step:** {message}")
            elif step_type == "test_cases":
                with test_cases_box.container():
                    st.markdown(message)
            elif step_type == "execution_log":
                with execution_box.container():
                    st.code(message, language="bash")
            elif step_type == "healer_log":
                # Append the message to our list and render all of them
                healer_messages.append(message)
                with healer_box.container():
                    for msg in healer_messages:
                        if "passed" in msg.lower():
                            st.markdown("✅ " + msg)
                        elif "failing" in msg.lower():
                            st.markdown("❌ " + msg)
                        else:
                            st.markdown("⚠️ " + msg)
            elif step_type == "report":
                with report_box.container():
                    st.markdown(message)

        # Run the pipeline
        try:
            with st.spinner("AI Agents are working... Please wait."):
                run_qa_pipeline(user_story, ui_callback)
            status_text.success("✅ Pipeline Execution Complete!")
            st.balloons()
        except Exception as e:
            st.error(f"An error occurred: {str(e)}")