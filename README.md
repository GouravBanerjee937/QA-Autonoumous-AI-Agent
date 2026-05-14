# QA Autonomous AI Agent

This project is a fully autonomous, AI-powered Quality Assurance pipeline built with **CrewAI**, **Playwright**, and **Streamlit**. It takes a plain-English User Story or PRD, generates a test plan, writes the Python Playwright code, executes the tests, heals the code if it fails, and generates a final report.

## 🚀 Features
* **Test Planner Agent:** Analyzes requirements and outputs a structured Markdown test plan.
* **Test Generator Agent:** Writes dynamic, synchronous `pytest-playwright` code based on the plan.
* **Test Healer Agent:** Automatically analyzes Pytest failure logs and rewrites the test code up to 3 times to fix incorrect assumptions or locators.
* **QA Reporter Agent:** Generates a final `final_qa_report.md` summarizing the results.
* **Web Interface:** A cyberpunk-themed Streamlit UI to monitor the agents in real-time.
* **Document Uploader:** Supports `.pdf` and `.docx` uploads to extract requirements automatically.

## 🛠 Prerequisites

1. Python 3.12+
2. Node.js (for Playwright dependencies)
3. An OpenAI API Key

## 💻 Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/GouravBanerjee937/QA-Autonoumous-AI-Agent.git
   cd QA-Autonoumous-AI-Agent
   ```

2. **Create a virtual environment:**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows use: .venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Install Playwright Browsers:**
   *(Note: The `conftest.py` is currently configured to use your local Google Chrome installation, but it is best practice to install the Playwright binaries).*
   ```bash
   playwright install
   ```

## 🔑 Configuration
Create a `.env` file in the root directory of the project and add your OpenAI API Key:

```env
OPENAI_API_KEY=your-sk-api-key-here
```
> **Note:** The `.env` file is included in `.gitignore` and will never be pushed to GitHub.

## 🏃 Usage
Start the Streamlit web interface:

```bash
streamlit run Home.py
```
1. Paste your User Story (or upload a PRD document).
2. Click **Run QA Pipeline**.
3. Watch the agents plan, code, execute, heal, and report live!
