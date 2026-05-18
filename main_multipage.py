import os
import sys
import logging
import subprocess
import ast
import json
import re
from urllib.parse import urlparse
from dotenv import load_dotenv
from crewai import Agent, Task, Crew, Process
from crewai.tools import tool
from playwright.sync_api import sync_playwright

import prompts

# ==========================================
# 1. SETUP & CONFIGURATION
# ==========================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("qa_agent_multipage.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("QA_Multipage_Agent_System")

load_dotenv()
if not os.getenv("OPENAI_API_KEY"):
    logger.error("OPENAI_API_KEY is not set. Please add it to your .env file.")
    raise ValueError("Missing OPENAI_API_KEY in environment variables.")

MODEL_NAME = "gpt-4o"

# ==========================================
# 2. DEFINE AGENTS
# ==========================================
gherkin_translator = Agent(
    role=prompts.ROLE_GHERKIN_TRANSLATOR,
    goal=prompts.GOAL_GHERKIN_TRANSLATOR,
    backstory=prompts.BACKSTORY_GHERKIN_TRANSLATOR,
    verbose=True,
    allow_delegation=False,
    llm=MODEL_NAME
)

test_planner = Agent(
    role=prompts.ROLE_TEST_PLANNER,
    goal=prompts.GOAL_TEST_PLANNER,
    backstory=prompts.BACKSTORY_TEST_PLANNER,
    verbose=True,
    allow_delegation=False,
    llm=MODEL_NAME
)

dom_filter_agent = Agent(
    role=prompts.ROLE_DOM_FILTER,
    goal=prompts.GOAL_DOM_FILTER,
    backstory=prompts.BACKSTORY_DOM_FILTER,
    verbose=True,
    allow_delegation=False,
    llm=MODEL_NAME
)

test_generator = Agent(
    role=prompts.ROLE_TEST_GENERATOR,
    goal=prompts.GOAL_TEST_GENERATOR,
    backstory=prompts.BACKSTORY_TEST_GENERATOR,
    verbose=True,
    allow_delegation=False,
    llm=MODEL_NAME
)

test_healer = Agent(
    role=prompts.ROLE_TEST_HEALER,
    goal=prompts.GOAL_TEST_HEALER,
    backstory=prompts.BACKSTORY_TEST_HEALER,
    verbose=True,
    allow_delegation=False,
    llm=MODEL_NAME
)

qa_reporter = Agent(
    role=prompts.ROLE_QA_REPORTER,
    goal=prompts.GOAL_QA_REPORTER,
    backstory=prompts.BACKSTORY_QA_REPORTER,
    verbose=True,
    allow_delegation=False,
    llm=MODEL_NAME
)

# ==========================================
# 3. HELPER FUNCTIONS & INTERACTIVE SCOUT
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
    process = subprocess.run([sys.executable, "-m", "pytest", "generated_test_multipage.py", "-v"], capture_output=True, text=True)
    return process.stdout + "\n" + process.stderr, process.returncode

class PlaywrightStaticAnalyzer(ast.NodeVisitor):
    def __init__(self):
        self.errors = []
    
    def visit_Call(self, node):
        if isinstance(node.func, ast.Attribute):
            if node.func.attr == 'get_by_role':
                if len(node.args) > 0 and isinstance(node.args[0], ast.Constant) and node.args[0].value == 'button':
                    has_exact = any(kw.arg == 'exact' for kw in node.keywords)
                    if not has_exact:
                        self.errors.append(f"Line {node.lineno}: `get_by_role('button', ...)` is missing `exact=True`. This causes strict mode violations.")
            elif node.func.attr == 'locator':
                if len(node.args) > 0 and isinstance(node.args[0], ast.Constant):
                    val = node.args[0].value
                    if isinstance(val, str):
                        if '.css-' in val or '.Mui' in val:
                            self.errors.append(f"Line {node.lineno}: Brittle CSS class found in locator: '{val}'. You MUST use semantic locators (e.g., get_by_placeholder, get_by_role).")
        self.generic_visit(node)

def analyze_code_statically(code: str) -> list[str]:
    try:
        tree = ast.parse(code)
        analyzer = PlaywrightStaticAnalyzer()
        analyzer.visit(tree)
        return analyzer.errors
    except SyntaxError as e:
        return [f"SyntaxError: The generated code is not valid Python. {e}"]

def parse_pytest_log_for_passed_tests(log: str) -> list[str]:
    passed_tests = []
    for line in log.split('\n'):
        if " PASSED " in line and "generated_test_multipage.py::" in line:
            parts = line.split("::")
            if len(parts) > 1:
                test_name = parts[1].split(" ")[0].split("[")[0] 
                if test_name not in passed_tests:
                    passed_tests.append(test_name)
    return passed_tests

def extract_functions(source_code: str) -> dict[str, str]:
    try:
        tree = ast.parse(source_code)
    except SyntaxError:
        return {}
    
    functions = {}
    lines = source_code.splitlines()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            start_line = node.lineno - len(node.decorator_list) - 1 
            if node.decorator_list:
                start_line = min(d.lineno for d in node.decorator_list) -1
            end_line = node.end_lineno
            functions[node.name] = "\n".join(lines[start_line:end_line])
    return functions

def stitch_healed_code(original_code: str, healed_code: str, passed_tests: list[str]) -> str:
    orig_funcs = extract_functions(original_code)
    healed_funcs = extract_functions(healed_code)
    
    if not orig_funcs or not healed_funcs:
        return healed_code
        
    final_code_lines = []
    
    try:
        tree = ast.parse(original_code)
        import_lines = []
        lines = original_code.splitlines()
        for node in tree.body:
            if not isinstance(node, ast.FunctionDef):
                start = node.lineno - 1
                end = node.end_lineno
                import_lines.extend(lines[start:end])
        final_code_lines.extend(import_lines)
    except SyntaxError:
        pass

    final_code_lines.append("") 

    all_func_names = list(orig_funcs.keys())
    for f in healed_funcs.keys():
        if f not in all_func_names:
            all_func_names.append(f)
            
    for func_name in all_func_names:
        if func_name in passed_tests and func_name in orig_funcs:
            final_code_lines.append(orig_funcs[func_name])
        elif func_name in healed_funcs:
            final_code_lines.append(healed_funcs[func_name])
        elif func_name in orig_funcs: 
             final_code_lines.append(orig_funcs[func_name])
             
        final_code_lines.append("") 
            
    return "\n".join(final_code_lines)

def extract_urls_from_story(text: str) -> list[str]:
    url_pattern = re.compile(r'https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+[^\s]*')
    urls = url_pattern.findall(text)
    return [url.rstrip('.,;)') for url in urls]

# ==========================================
# INTERACTIVE SCOUT (Playwright MCP-style Tools)
# ==========================================
class InteractiveScoutState:
    playwright_instance = None
    browser = None
    context = None
    page = None
    extracted_elements = []
    action_count = 0

# Need a global reference to ui_callback so tools can log live
GLOBAL_UI_CALLBACK = None

def _auto_extract_dom():
    InteractiveScoutState.action_count += 1
    loop_num = InteractiveScoutState.action_count
    
    try:
        current_url = InteractiveScoutState.page.url
        page_title = InteractiveScoutState.page.title()
        
        if GLOBAL_UI_CALLBACK:
            GLOBAL_UI_CALLBACK(f"### Loop {loop_num} for page: {page_title} ({current_url})", "scout")
            GLOBAL_UI_CALLBACK("Extracting DOM elements...", "scout")
             
        found_nodes = InteractiveScoutState.page.evaluate('''() => {
            const results = [];
            const nodes = document.querySelectorAll('input, button, a[href]');
            nodes.forEach(el => {
                if (el.offsetWidth > 0 && el.offsetHeight > 0) {
                    results.push({
                        tag: el.tagName.toLowerCase(),
                        type: el.type || undefined,
                        id: el.id || undefined,
                        name: el.name || undefined,
                        placeholder: el.placeholder || undefined,
                        text: el.innerText ? el.innerText.trim() : undefined,
                        href: el.href || undefined,
                        className: el.className || undefined
                    });
                }
            });
            return results;
        }''')
        
        if found_nodes:
            contextual_nodes = {
                "loop_number": loop_num,
                "page_url": current_url,
                "page_title": page_title,
                "elements": found_nodes
            }
            InteractiveScoutState.extracted_elements.append(contextual_nodes)
            
            if GLOBAL_UI_CALLBACK:
                 GLOBAL_UI_CALLBACK(f"Successfully extracted {len(found_nodes)} elements.", "scout")
                 GLOBAL_UI_CALLBACK(json.dumps(contextual_nodes, indent=2), "scout")
                 
    except Exception as e:
        if GLOBAL_UI_CALLBACK:
            GLOBAL_UI_CALLBACK(f"Error during auto DOM extraction: {str(e)}", "scout")

@tool("playwright_navigate")
def playwright_navigate(url: str) -> str:
    """Navigates the browser to a specific URL and automatically extracts the DOM."""
    try:
        if InteractiveScoutState.page is None:
            InteractiveScoutState.playwright_instance = sync_playwright().start()
            InteractiveScoutState.browser = InteractiveScoutState.playwright_instance.chromium.launch(headless=True, channel="chrome")
            InteractiveScoutState.context = InteractiveScoutState.browser.new_context(ignore_https_errors=True)
            InteractiveScoutState.page = InteractiveScoutState.context.new_page()
            InteractiveScoutState.action_count = 0
            
        if GLOBAL_UI_CALLBACK:
            GLOBAL_UI_CALLBACK(f"Navigating to URL: {url}", "scout")
            
        InteractiveScoutState.page.goto(url, timeout=60000, wait_until="load")
        InteractiveScoutState.page.wait_for_timeout(5000)
        
        _auto_extract_dom()
        return f"Successfully navigated to {url} and automatically extracted DOM elements."
    except Exception as e:
        if GLOBAL_UI_CALLBACK:
            GLOBAL_UI_CALLBACK(f"Error navigating to {url}: {str(e)}", "scout")
        return f"Error navigating to {url}: {str(e)}"

@tool("playwright_click")
def playwright_click(selector: str) -> str:
    """Clicks an element on the page using a CSS selector or text (e.g. input#email or text=Login) and automatically extracts the DOM."""
    try:
        if InteractiveScoutState.page is None:
             return "Error: Browser not open. Navigate first."
             
        if GLOBAL_UI_CALLBACK:
            GLOBAL_UI_CALLBACK(f"Clicking element: {selector}", "scout")
             
        # Use more robust clicking that waits for the element
        element = InteractiveScoutState.page.locator(selector).first
        element.wait_for(state="visible", timeout=15000)
        element.click(timeout=15000)
        InteractiveScoutState.page.wait_for_timeout(5000)
        
        _auto_extract_dom()
        return f"Successfully clicked {selector} and automatically extracted DOM elements."
    except Exception as e:
        if GLOBAL_UI_CALLBACK:
            GLOBAL_UI_CALLBACK(f"Error clicking {selector}: {str(e)}", "scout")
        return f"Error clicking {selector}: {str(e)}"

@tool("playwright_fill")
def playwright_fill(selector: str, text: str) -> str:
    """Fills an input element on the page using a CSS selector and automatically extracts the DOM."""
    try:
        if InteractiveScoutState.page is None:
             return "Error: Browser not open. Navigate first."
             
        if GLOBAL_UI_CALLBACK:
            GLOBAL_UI_CALLBACK(f"Filling element: {selector}", "scout")
             
        # Use more robust filling that waits for the element
        element = InteractiveScoutState.page.locator(selector).first
        element.wait_for(state="visible", timeout=15000)
        element.fill(text, timeout=15000)
        InteractiveScoutState.page.wait_for_timeout(2000)
        
        _auto_extract_dom()
        return f"Successfully filled {selector} with text and automatically extracted DOM elements."
    except Exception as e:
        if GLOBAL_UI_CALLBACK:
            GLOBAL_UI_CALLBACK(f"Error filling {selector}: {str(e)}", "scout")
        return f"Error filling {selector}: {str(e)}"

interactive_scout_agent = Agent(
    role='Interactive DOM Explorer',
    goal='Navigate a website, interact with it to complete a user flow, and let the tools extract DOM elements at every step.',
    backstory=(
        "You are an automated web crawler. You use Playwright tools to explore web pages. "
        "You have the ability to navigate, click buttons, and fill forms. "
        "Your job is to read a User Story, and then actually perform those steps in a live browser to ensure you expose all hidden fields. "
        "Every tool you use (navigate, click, fill) will AUTOMATICALLY extract the DOM in the background and save it. "
        "You do not need to call an extract tool. Just focus on following the user story steps exactly. "
        "CRITICAL: If you need to fill an email, look at the DOM output from the previous step. Use a precise selector like '#userName' or 'input[type=\"text\"]' rather than guessing 'input[type=\"email\"]'. "
        "If a tool call returns an Error, you must try a different selector."
    ),
    tools=[playwright_navigate, playwright_click, playwright_fill],
    verbose=True,
    allow_delegation=False,
    llm=MODEL_NAME
)

# ==========================================
# 4. DEFINE MULTIPAGE PIPELINE WITH CALLBACKS
# ==========================================
def run_multipage_pipeline(user_story: str, ui_callback=None):
    logger.info("Starting QA Agent Multipage Pipeline...")
    
    global GLOBAL_UI_CALLBACK
    GLOBAL_UI_CALLBACK = ui_callback

    def notify(message, step_type):
        if ui_callback:
            ui_callback(message, step_type)
        else:
            print(f"\n[{step_type.upper()}] {message}")

    # --- STEP 0: Translate to Gherkin ---
    notify("Agent 0 (Gherkin Translator) is forcefully converting the PRD to BDD syntax...", "status")
    gherkin_task = Task(
        description=prompts.TASK_GHERKIN_TRANSLATOR.format(user_story=user_story),
        expected_output="A clean Gherkin syntax scenario block.",
        agent=gherkin_translator
    )
    crew_gherkin = Crew(agents=[gherkin_translator], tasks=[gherkin_task], verbose=True)
    crew_gherkin.kickoff()
    gherkin_output = gherkin_task.output.raw
    
    notify(f"### Converted Gherkin Requirements:\n\n```gherkin\n{gherkin_output}\n```\n---", "test_cases")

    # --- STEP 1: Plan ---
    notify("Agent 1 (Test Planner) is generating test cases from Gherkin...", "status")
    plan_task = Task(
        description=prompts.TASK_TEST_PLANNER.format(gherkin_output=gherkin_output),
        expected_output="A markdown document containing structured test cases.",
        agent=test_planner
    )
    crew_plan = Crew(agents=[test_planner], tasks=[plan_task], verbose=True)
    crew_plan.kickoff()
    plan_output = plan_task.output.raw
    
    notify(f"### Generated Test Plan:\n\n{plan_output}", "test_cases")

    # --- STEP 1.5: INTERACTIVE SCOUT (DOM Discovery) ---
    urls = extract_urls_from_story(user_story)
    context_map = "No URL provided in the User Story. Generator must guess selectors."
    
    if urls:
        target_url = urls[0]
        notify(f"Interactive Scout Agent is launching to explore {target_url}...", "status")
        
        # Reset state
        InteractiveScoutState.extracted_elements = []
        InteractiveScoutState.action_count = 0
        
        scout_task = Task(
            description=(
                f"You need to follow this user story: {gherkin_output}\n\n"
                f"1. Call `playwright_navigate('{target_url}')`.\n"
                f"2. Look at the user story. If it says to fill in an email, call `playwright_fill` with a likely selector. Use '#userName' or 'input[placeholder=\"Mobile / Email\"]' if you are on mazu.in.\n"
                f"3. If it says to click next/login, call `playwright_click` on that button. Use 'button:has-text(\"Login\")'.\n"
                "Stop once you have completed the basic flow or if you get stuck. The tools will auto-extract the DOM for you."
            ),
            expected_output="A brief summary of what you clicked and explored.",
            agent=interactive_scout_agent
        )
        
        try:
            crew_scout = Crew(agents=[interactive_scout_agent], tasks=[scout_task], verbose=True)
            crew_scout.kickoff()
        finally:
            if InteractiveScoutState.browser:
                try:
                    InteractiveScoutState.browser.close()
                    InteractiveScoutState.playwright_instance.stop()
                except:
                    pass
                InteractiveScoutState.browser = None
                InteractiveScoutState.page = None
                InteractiveScoutState.context = None
                InteractiveScoutState.playwright_instance = None
        
        # Combine all extracted DOM states from memory
        scout_raw_json = json.dumps(InteractiveScoutState.extracted_elements, indent=2)
        
        print("\n" + "="*50)
        print("🔍 INTERACTIVE SCOUT DOM DUMP RESULTS (COMBINED):")
        print("="*50)
        print(scout_raw_json)
        print("="*50 + "\n")
        
        if ui_callback:
             ui_callback(scout_raw_json, "scout")
        
        if InteractiveScoutState.extracted_elements:
            notify("Filter Agent is analyzing the combined raw DOM data from all steps...", "status")
            filter_task = Task(
                description=prompts.TASK_DOM_FILTER.format(gherkin_output=gherkin_output, target_url=target_url, scout_raw_json=scout_raw_json),
                expected_output="A Markdown mapping of logical elements (e.g., 'Email Input', 'Login Button', 'Password Input') to their exact CSS locators based on the JSON.",
                agent=dom_filter_agent
            )
            crew_filter = Crew(agents=[dom_filter_agent], tasks=[filter_task], verbose=True)
            crew_filter.kickoff()
            context_map = filter_task.output.raw
            notify(context_map, "filter")
            
            print("\n" + "="*50)
            print("🗺️ LLM FILTER AGENT CONTEXT MAP:")
            print("="*50)
            print(context_map)
            print("="*50 + "\n")

        else:
            context_map = f"Scout failed to find any elements. Generator must fall back to robust selector guessing."

    # --- STEP 2: Generate Code ---
    notify("Agent 2 (Test Generator) is writing Playwright code...", "status")
    code_task = Task(
        description=prompts.TASK_TEST_GENERATOR.format(plan_output=plan_output, context_map=context_map),
        expected_output="Raw Python script using Playwright and pytest.",
        agent=test_generator
    )
    crew_code = Crew(agents=[test_generator], tasks=[code_task], verbose=True)
    crew_code.kickoff()
    
    code_output = clean_python_code(code_task.output.raw)
    
    # --- STATIC ANALYSIS (Pre-Execution Validation) ---
    notify("Running Static Analyzer to catch Playwright hallucinations...", "status")
    static_errors = analyze_code_statically(code_output)
    
    if static_errors:
        notify(f"Static Analyzer caught {len(static_errors)} error(s) before execution! Sending to Healer...", "healer_log")
        for err in static_errors:
            notify(f"⚠️ {err}", "healer_log")
            
        heal_task = Task(
            description=prompts.TASK_TEST_HEALER_STATIC.format(code_output=code_output, static_errors_json=json.dumps(static_errors, indent=2)),
            expected_output="The fixed raw Python script.",
            agent=test_healer
        )
        crew_heal = Crew(agents=[test_healer], tasks=[heal_task], verbose=True)
        crew_heal.kickoff()
        code_output = clean_python_code(heal_task.output.raw)
        notify("Static Analysis fixes applied.", "healer_log")
    else:
        notify("Static Analysis Passed: Code is clean of known anti-patterns.", "healer_log")

    notify(code_output, "code")
    with open("generated_test_multipage.py", "w") as f:
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
        
        passed_tests = parse_pytest_log_for_passed_tests(test_log)
        if passed_tests:
            logger.info(f"Passed tests to protect: {passed_tests}")
            
        heal_task = Task(
            description=prompts.TASK_TEST_HEALER_RUNTIME.format(current_code=current_code, test_log=test_log),
            expected_output="The fully rewritten and fixed raw Python script.",
            agent=test_healer
        )
        crew_heal = Crew(agents=[test_healer], tasks=[heal_task], verbose=True)
        crew_heal.kickoff()
        
        raw_healed_code = clean_python_code(heal_task.output.raw)
        
        if passed_tests:
            healed_code = stitch_healed_code(current_code, raw_healed_code, passed_tests)
        else:
            healed_code = raw_healed_code
            
        with open("generated_test_multipage.py", "w") as f:
            f.write(healed_code)
            
        current_code = healed_code
        healer_log_message = f"### Heal Attempt {heal_attempt}\n\nHealer Agent analyzed the failure and rewrote the script.\n(Protected {len(passed_tests)} passed tests).\n\n```python\n{healed_code}\n```\n"
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
        description=prompts.TASK_QA_REPORTER.format(plan_output=plan_output, test_log=test_log, heal_attempt=heal_attempt),
        expected_output="A Markdown document containing a summary of the test cases, status, and comments.",
        agent=qa_reporter
    )
    crew_report = Crew(agents=[qa_reporter], tasks=[report_task], verbose=True)
    crew_report.kickoff()
    report_output = report_task.output.raw

    with open("final_qa_report_multipage.md", "w") as f:
        f.write(report_output)
    
    notify(report_output, "report")
    return report_output
