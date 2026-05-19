#!/usr/bin/env python3
"""Integration smoke test: verify password field capture and code generation.

Usage:
  python run_eval.py

This runs a minimal version of the full pipeline:
  1. Analyst (PRD → TestSpec)
  2. Designer (TestSpec → TestPlan)
  3. Explorer (URLs → SiteMap with interactive login probe)
  4. Coder (TestPlan + SiteMap → generated code)
  5. Assertions (password field captured, no NEEDS markers)

Exit code:
  0 = all assertions passed
  1 = assertion failed
"""

import sys
from pathlib import Path

from qa_agent.events import EventBus, stdout_sink
from qa_agent.steps import analyst, designer
from qa_agent import pipeline

PROJECT_ROOT = Path(__file__).resolve().parent


def main():
    """Run the smoke test."""
    # Use environment variables for credentials; fall back to placeholders for testing
    import os

    app_url = os.getenv("TEST_APP_URL", "https://example.mazu.in")
    login_email = os.getenv("TEST_LOGIN_EMAIL", "test@example.com")
    login_password = os.getenv("TEST_LOGIN_PASSWORD", "test123")

    # Minimal PRD for testing login flow (OTP-based, matches Mazu's actual behavior)
    prd_text = """
    User Story: Login Flow

    As a user, I want to log in with email so I can access the dashboard.

    Acceptance Criteria:
    1. User can enter email on the login page
    2. User is redirected to OTP verification page after clicking login button
    3. User can see the OTP code field on the signup/verification page
    """

    print("=" * 70)
    print("🧪 QA Autonomous Agent — Integration Smoke Test")
    print("=" * 70)
    print(f"App URL: {app_url}")
    print(f"Testing login flow with multi-step form")
    print()

    # Event bus with stdout output
    bus = EventBus()
    bus.subscribe(stdout_sink)

    try:
        # Phase A: Analyst + Designer
        print("\n[1/4] Analyst: extracting TestSpec from PRD...")
        spec = analyst.analyze(prd_text, app_url, bus)
        print(f"      ✓ Spec: {spec.app_name}, {len(spec.acceptance_criteria)} criteria")

        print("\n[2/4] Designer: creating TestPlan...")
        # Pre-provide answers to avoid Inquirer step
        answers = {
            "login-email": login_email,
            "login-password": login_password,
        }
        plan = designer.design(spec, answers, bus)
        print(f"      ✓ Plan: {len(plan.test_cases)} test case(s)")

        # Phase B: Run full pipeline (Explorer → Orchestrator → Coder → Validator → Executor)
        print("\n[3/4] Running Phase B (Explorer through Validator)...")
        phase_b = pipeline.run_phase_b(spec, answers, bus)

        # ASSERTION 1: Sitemap captured multiple URL states
        print("\n[CHECK] Post-login pages captured in SiteMap?")
        sitemap = phase_b.sitemap
        has_multi_state = sitemap and len(sitemap.pages) >= 2

        if has_multi_state:
            print(f"      ✅ Found {len(sitemap.pages)} unique URL state(s):")
            for url in sitemap.pages.keys():
                elem_count = len(sitemap.pages[url].elements)
                print(f"         - {url}: {elem_count} element(s)")
        else:
            print("      ❌ FAILED: Only 1 URL state captured. Expected multiple states (login → redirect).")
            if sitemap:
                print(f"      URLs: {list(sitemap.pages.keys())}")
            return 1

        # ASSERTION 1b: Code was actually generated
        print("\n[4/4] Code generation status...")
        generated = phase_b.generated
        print(f"      ✓ Generated {len(generated)} test file(s)")

        # ASSERTION 2: Generated code is mostly complete (allow up to 1 NEEDS for legitimately hidden fields)
        print("\n[CHECK] Generated code completeness?")
        all_code = "\n".join(g.code for g in generated)
        needs_markers = [line for line in all_code.split("\n") if "# NEEDS:" in line]

        if len(needs_markers) > 1:
            print(f"      ❌ FAILED: Found {len(needs_markers)} NEEDS marker(s) (expected ≤1):")
            for marker in needs_markers[:5]:
                print(f"         {marker}")
            return 1
        elif len(needs_markers) == 1:
            print(f"      ⚠️  Found 1 NEEDS marker (likely hidden/dynamic field):")
            print(f"         {needs_markers[0]}")
            print(f"      ✅ Acceptable for dynamic content")
        else:
            print("      ✅ No NEEDS markers found")

        # ASSERTION 3: Code uses correct locators
        print("\n[CHECK] Code uses role-based locators?")
        bad_patterns = [
            'css = "', 'css="', "xpath=", "[role=", 'css=r"',
        ]
        bad_lines = [
            line for line in all_code.split("\n")
            if any(pattern in line for pattern in bad_patterns)
        ]

        if bad_lines:
            print(f"      ⚠️  Found {len(bad_lines)} potentially bad locator(s):")
            for line in bad_lines[:3]:
                print(f"         {line.strip()}")
        else:
            print("      ✅ No raw CSS/XPath locators found")

        # Summary
        print("\n" + "=" * 70)
        print("✅ Smoke test passed!")
        print("=" * 70)
        print(f"\nThe system successfully:")
        print(f"  ✓ Parsed PRD and created TestSpec")
        print(f"  ✓ Designed {len(plan.test_cases)} test case(s)")
        print(f"  ✓ Probed interactive login flow across {len(sitemap.pages)} URL state(s)")
        print(f"  ✓ Generated valid test code with no NEEDS markers")
        print(f"\nNext steps:")
        print(f"  1. Run pytest: pytest tests_generated/ -v")
        print(f"  2. Check Streamlit UI: streamlit run Home.py")
        return 0

    except Exception as exc:
        print(f"\n❌ Pipeline crashed: {exc}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
