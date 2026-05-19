from playwright.sync_api import Page, expect

def test_user_can_enter_email_on_the_login_page(page: Page, snap):
    page.goto("https://app.mazu.in/login")
    snap("after navigate to login")

    email_input = page.get_by_role("textbox", name="Mobile / Email", exact=True)
    email_input.fill("testuser@example.com")
    snap("after fill email")

    expect(email_input).to_have_value("testuser@example.com")
    snap("verify email input value")
