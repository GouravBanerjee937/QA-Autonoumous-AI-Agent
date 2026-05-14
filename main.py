import os
import sys
import logging
import subprocess
from dotenv import load_dotenv
from crewai import Agent, Task, Crew, Process

# ==========================================
# 1. SETUP & CONFIGURATION
# ==========================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("qa_agent.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("QA_Agent_System")

load_dotenv()
if not os.getenv("OPENAI_API_KEY"):
    logger.error("OPENAI_API_KEY is not set. Please add it to your .env file.")
    raise ValueError("Missing OPENAI_API_KEY in environment variables.")

# ==========================================
# 2. DEFINE AGENTS
# ==========================================
test_planner = Agent(
    role='Senior QA Test Planner',
    goal='Analyze user stories and requirements to create comprehensive test plans.',
    backstory="You are an expert QA Architect. Your job is to read product requirements and break them down into structured test cases.",
    verbose=True,
    allow_delegation=False,
    llm="gpt-4o"
)

test_generator = Agent(
    role='Playwright Automation Engineer',
    goal='Translate test plans into executable Playwright-Python automation scripts.',
    backstory=(
        "You specialize in writing clean, reliable Playwright code in Python using pytest. "
        "CRITICAL RULES: "
        "1. Avoid asserting exact page titles or exact text unless explicitly stated in the PRD. Use 'contains' logic or verify core visibility. "
        "2. For inputs like Email/Mobile, use robust CSS selectors like `input[type='text'], input[type='email'], input[placeholder*='email' i]` as sites often use 'text' for dual-purpose fields. "
        "3. When using the `page` fixture, just use `def test_example(page):` without any type annotations. "
        "4. NEVER import anything from `playwright.async_api`. Always write synchronous tests."
        "5. NEVER use `@pytest.mark.asyncio` decorator. All Playwright code must be fully synchronous."
        "6. NEVER create your own `setup`, `teardown`, `browser`, `context`, or `page` fixtures! "
        "   CRITICAL: The environment already has a `page` fixture built-in! If you redefine `page` inside generated_test.py, it will crash. "
        "   Just write the test functions directly (e.g., `def test_login(page):`). Do NOT include any `@pytest.fixture` blocks in your output."
    ),
    verbose=True,
    allow_delegation=False,
    llm="gpt-4o"
)

test_healer = Agent(
    role='QA Automation Healer',
    goal='Analyze failed Playwright test logs, identify incorrect assumptions/selectors, and rewrite the code to fix the tests.',
    backstory=(
        "You are an expert debugging assistant. When a UI test fails, you look at the pytest error log. "
        "If a selector timed out (e.g., waiting for input[type='email']), you rewrite the code using a broader selector. "
        "If an assertion failed (e.g., page title mismatch), you update the assertion to match the reality seen in the logs. "
        "CRITICAL HEALER RULES:"
        "1. NEVER output asynchronous code. NEVER use `@pytest.mark.asyncio`. If the failed code had it, REMOVE IT."
        "2. NEVER output your own `setup`, `teardown`, `browser`, `context`, or `page` fixtures! The environment already provides `page`. "
        "   If the failed code contained `@pytest.fixture(scope=\"function\")\\ndef page():...`, REMOVE IT ENTIRELY."
        "You output ONLY valid, fully rewritten synchronous Python code without markdown blocks."
    ),
    verbose=True,
    allow_delegation=False,
    llm="gpt-4o"
)

qa_reporter = Agent(
    role='QA Reporting Analyst',
    goal='Generate a final Markdown report summarizing the test cases, their execution status, and comments.',
    backstory="You are a detail-oriented QA Manager. Your job is to take the final outputs and test execution logs to create a clean summary report.",
    verbose=True,
    allow_delegation=False,
    llm="gpt-4o"
)

# ==========================================
# 3. HELPER FUNCTIONS
# ==========================================
def clean_python_code(raw_output: str) -> str:
    code = raw_output
    if code.startswith("```python"):
        code = code.replace("```python", "", 1)
    if code.endswith("```"):
        code = code.rsplit("```", 1)[0]
    elif "```" in code:
        code = code.split("```python")[-1].split("```")[0]
        
    lines = code.split('\n')
    clean_lines = []
    for line in lines:
        if line.strip().lower().startswith("note:") or line.strip().lower().startswith("here is the"):
            break
        clean_lines.append(line)
    return '\n'.join(clean_lines).strip()

def run_tests():
    process = subprocess.run([sys.executable, "-m", "pytest", "generated_test.py", "-v"], capture_output=True, text=True)
    return process.stdout + "\n" + process.stderr, process.returncode

# ==========================================
# 4. DEFINE PIPELINE WITH CALLBACKS
# ==========================================
def run_qa_pipeline(user_story: str, ui_callback=None):
    logger.info("Starting QA Agent Pipeline...")

    def notify(message, step_type):
        if ui_callback:
            ui_callback(message, step_type)
        else:
            print(f"\n[{step_type.upper()}] {message}")

    # --- STEP 1: Plan ---
    notify("Agent 1 (Test Planner) is generating test cases...", "status")
    plan_task = Task(
        description=f"Analyze this user story and generate a detailed test plan:\n\n{user_story}",
        expected_output="A markdown document containing structured test cases.",
        agent=test_planner
    )
    crew_plan = Crew(agents=[test_planner], tasks=[plan_task], verbose=True)
    crew_plan.kickoff()
    plan_output = plan_task.output.raw
    notify(plan_output, "test_cases")

    # --- STEP 2: Generate Code ---
    notify("Agent 2 (Test Generator) is writing Playwright code...", "status")
    code_task = Task(
        description=(
            f"Based on this test plan:\n{plan_output}\n\n"
            "Write a complete Playwright Python script using pytest. "
            "Output ONLY valid python code. Do not wrap in ```python blocks. "
            "CRITICAL: Avoid strict text/title assertions unless in the PRD. Use robust locators."
        ),
        expected_output="Raw Python script using Playwright and pytest.",
        agent=test_generator
    )
    crew_code = Crew(agents=[test_generator], tasks=[code_task], verbose=True)
    crew_code.kickoff()
    
    code_output = clean_python_code(code_task.output.raw)
    with open("generated_test.py", "w") as f:
        f.write(code_output)
    
    # --- STEP 3: Execute Test (First Pass) ---
    notify("Executing Initial Test Run...", "status")
    test_log, return_code = run_tests()
    notify(f"Initial Execution Output:\n\n{test_log}", "execution_log")

    # --- STEP 4: Healer Phase (Loop up to 3 times) ---
    max_heal_attempts = 3
    heal_attempt = 0
    current_code = code_output
    
    while return_code != 0 and heal_attempt < max_heal_attempts and ("FAILED" in test_log or "ERROR" in test_log):
        heal_attempt += 1
        notify(f"Agent 3 (Test Healer) detected failures! Starting Heal Attempt {heal_attempt}/{max_heal_attempts}...", "status")
        
        heal_task = Task(
            description=(
                f"The previously generated test code failed. Here is the code:\n{current_code}\n\n"
                f"Here is the pytest error log:\n{test_log}\n\n"
                "Analyze the errors. If assertions failed (like page.title()), update them to match the actual reality shown in the logs. "
                "If selectors timed out, rewrite them to be more generic (e.g., use page.locator(\"input\").nth(0) or similar fallback logic). "
                "If you see errors about 'async fixture' or 'pytest.mark.asyncio', REMOVE all async/await syntax and decorators and ensure the script is purely synchronous using standard pytest fixtures. "
                "If you see 'BrowserType.launch: Executable doesn't exist', it means you incorrectly generated a `@pytest.fixture` block for `browser` or `page` inside the test file. You MUST delete any `setup`, `browser`, or `page` fixture definitions in your output. Only output the test functions."
                "Rewrite the FULL Python script with the fixes. Output ONLY valid python code without markdown formatting."
            ),
            expected_output="The fully rewritten and fixed raw Python script.",
            agent=test_healer
        )
        crew_heal = Crew(agents=[test_healer], tasks=[heal_task], verbose=True)
        crew_heal.kickoff()
        
        healed_code = clean_python_code(heal_task.output.raw)
        with open("generated_test.py", "w") as f:
            f.write(healed_code)
            
        current_code = healed_code
        healer_log_message = f"### Heal Attempt {heal_attempt}\n\nHealer Agent analyzed the failure and rewrote the script.\n\n```python\n{healed_code}\n```\n"
        notify(healer_log_message, "healer_log")
        
        notify(f"Executing Healed Test Run (Attempt {heal_attempt})...", "status")
        test_log, return_code = run_tests()
        notify(f"Healed Execution Output (Attempt {heal_attempt}):\n\n{test_log}", "execution_log")
        
    if return_code == 0:
        if heal_attempt > 0:
            notify(f"✅ Tests passed successfully after {heal_attempt} heal attempt(s)!", "healer_log")
        else:
            notify("No healing required! Tests passed on the first try.", "healer_log")
    elif heal_attempt == max_heal_attempts:
        notify(f"❌ Tests still failing after {max_heal_attempts} heal attempts. Moving to reporting.", "healer_log")

    # --- STEP 5: Report ---
    notify("Agent 4 (QA Reporter) is writing the final report...", "status")
    report_task = Task(
        description=(
            f"Test Plan:\n{plan_output}\n\n"
            f"Final Test Execution Log:\n{test_log}\n\n"
            "Create a final summary report in Markdown format. "
            "For each test case, include a table with: 'Test Case Name', 'Status (Passed/Failed/Others)', and 'Comments'. "
            f"If the tests had to be healed, mention that it took {heal_attempt} heal attempt(s)."
        ),
        expected_output="A Markdown document containing a summary of the test cases, status, and comments.",
        agent=qa_reporter
    )
    crew_report = Crew(agents=[qa_reporter], tasks=[report_task], verbose=True)
    crew_report.kickoff()
    report_output = report_task.output.raw

    with open("final_qa_report.md", "w") as f:
        f.write(report_output)
    
    notify(report_output, "report")
    return report_output

if __name__ == "__main__":
    sample_user_story = "Go to https://app.mazu.in/login, enter email gouravbanerjee777@gmail.com, password Namita@2026 and login."
    run_qa_pipeline(sample_user_story)
