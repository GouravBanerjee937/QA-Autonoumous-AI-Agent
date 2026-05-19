from playwright.sync_api import Page, expect
import re

def test_user_is_redirected_to_otp_verification_page_after_clicking_login_button(page: Page, snap):
    # Given the user is on the login page at /login
    page.goto("https://app.mazu.in/login")
    snap("after navigate to login")

    # When the user types their email testuser@example.com into the email input field with id 'email'
    email_input = page.get_by_role("textbox", name="Mobile / Email", exact=True)
    email_input.fill("testuser@example.com")
    snap("after fill email")

    # And the user clicks the login button with id 'login-button'
    login_button = page.get_by_role("button", name="Login", exact=True)
    login_button.click()
    snap("after click login")

    # Then the user is redirected to the OTP verification page at /otp-verification
    expect(page).to_have_url(re.compile(r"https://app\.mazu\.in/otp-verification"))
    snap("verify otp verification page")
