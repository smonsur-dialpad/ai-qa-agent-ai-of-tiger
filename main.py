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
Generate **runnable Playwright E2E test(s) in Python (pytest)** using the following inputs:

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
1. Treat the Jira description as **acceptance criteria** with Preconditions, Steps, and Expected Results.
2. Map each step into Playwright async actions.
3. Include imports, pytest fixtures, and test functions.
4. Use the selectors provided above whenever possible (fall back to semantic text selectors if needed).
5. Always generate a **complete runnable pytest file** — no explanation or markdown fences.
6. Add comments above each block to describe what is being tested.
7. If the Jira/PR describes a **UI text replacement or copy change**:
   - Assert that the old text does NOT appear.
   - Assert that the new text DOES appear and is visible.
8. If inputs (e.g., phone numbers, emails) are mentioned in Jira, use those values explicitly in the test.
9. Ensure tests cover both positive and negative paths implied by the Jira description.
"""


    resp = client.messages.create(
        model="claude-3-haiku-20240307",
        max_tokens=800,
        messages=[{"role": "user", "content": prompt}]
    )

    return {"playwright_test": resp.content[0].text}