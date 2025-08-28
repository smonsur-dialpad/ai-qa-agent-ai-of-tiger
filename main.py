from fastapi import FastAPI, Request
import httpx
import os
from anthropic import Anthropic

app = FastAPI()

# Claude client
client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# Env vars for Jira + GitHub
JIRA_BASE = os.getenv("JIRA_BASE")  # e.g. https://dialpad.atlassian.net
JIRA_EMAIL = os.getenv("JIRA_EMAIL")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN")
GITHUB_TOKEN = os.getenv("DP_QA_GH_TOKEN")
GITHUB_REPO = os.getenv("DP_QA_GH_REPO")

# App creds (kept outside Jira)
APP_URL = os.getenv("APP_URL", "https://dialpad-mini.lovable.app/")
APP_USER = os.getenv("APP_USER", "demo@dialpad.com")
APP_PASS = os.getenv("APP_PASS", "password123")


@app.get("/")
def root():
    return {"message": "AI QA Agent is running 🚀"}


@app.post("/generate-tests")
async def generate_tests(req: Request):
    data = await req.json()
    jira_id = data.get("jira_id")
    pr_number = data.get("pr_number")

    # --- Fetch Jira Ticket ---
    async with httpx.AsyncClient() as client_http:
        jira_url = f"{JIRA_BASE}/rest/api/3/issue/{jira_id}"
        auth = (JIRA_EMAIL, JIRA_API_TOKEN)
        jira_resp = await client_http.get(jira_url, auth=auth)
        jira_resp.raise_for_status()
        jira_data = jira_resp.json()
        jira_title = jira_data["fields"]["summary"]
        jira_desc = jira_data["fields"]["description"]["content"][0]["content"][0]["text"]

    # --- Fetch GitHub PR Diff ---
    async with httpx.AsyncClient() as client_http:
        gh_url = f"https://api.github.com/repos/{GITHUB_REPO}/pulls/{pr_number}"
        headers = {
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3.diff"
        }
        pr_resp = await client_http.get(gh_url, headers=headers)
        pr_resp.raise_for_status()
        pr_diff = pr_resp.text

    # --- Prompt with selectors + flow ---
    prompt = f"""
You are an expert SDET.
Generate **a full Playwright E2E pytest file in Python** using the following inputs.

Jira Ticket {jira_id}:
Title: {jira_title}
Description:
{jira_desc}

GitHub PR Diff:
{pr_diff}

Application under test:
- Base URL: {APP_URL}
- Credentials: email = {APP_USER}, password = {APP_PASS}

Selectors cheat sheet:
- Login link: text="Login"
- Email input: #username
- Password input: #password
- Sign In button: text="Sign In"
- "Make a call" section: text="Make a call"
- Phone number input: #phone
- Start call button: text="Start a call"
- Call status text: #call-status
- End Call button: text="End Call"
- Close button: text="Close"
- Logout button: text="Log Out"

Instructions:
1. Parse the Jira description as **acceptance criteria** (preconditions, steps, expected results).
2. From these acceptance criteria + PR diff, **derive the complete set of test scenarios required for full coverage.**
   - Include all positive, negative, and edge cases implied by the Jira/PR.
   - If multiple flows or inputs are mentioned, cover each in a separate pytest test function.
   - Ensure **100% coverage of requirements** (do not omit corner cases).
3. For each scenario, generate a **separate pytest test function** with a descriptive name.
4. Use pytest fixtures for browser/page setup (no test should depend on another).
5. Always output a **single, complete, runnable pytest file** (no explanation, no markdown fences).
6. Add comments above each test explaining its purpose.
7. For UI text replacement or copy changes:
   - Assert that the old text is NOT visible.
   - Assert that the new text IS visible.
8. Use explicit values from Jira (e.g., phone number `123456789`) wherever given.
"""


    resp = client.messages.create(
        model="claude-3-haiku-20240307",
        max_tokens=800,
        messages=[{"role": "user", "content": prompt}]
    )

    return {"playwright_test": resp.content[0].text}