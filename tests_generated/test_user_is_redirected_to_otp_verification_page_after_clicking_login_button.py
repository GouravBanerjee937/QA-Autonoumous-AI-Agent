from playwright.sync_api import Page, expect
import re

def test_user_is_redirected_to_otp_verification_page_after_clicking_login_button(page: Page, snap):
    page.goto("https://app.mazu.in/login")
    snap("after navigate to login")

    email_input = page.get_by_role("textbox", name="Mobile / Email", exact=True)
    email_input.fill("testuser@example.com")
    snap("after fill email")

    login_button = page.get_by_role("button", name="Login", exact=True)
    login_button.click()
    snap("after click login")

    expect(page).to_have_url(re.compile(r"https://app\.mazu\.in/otp-verification"))
    snap("verify redirected to otp verification")
