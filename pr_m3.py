import os
import subprocess
import json
import requests
import re
import sys
import shutil
from github import Github
from rich.console import Console
from rich.progress import Progress
from threading import Timer

console = Console()
OLLAMA_API_URL = "http://localhost:11434/api/generate"
MODEL_NAME = os.getenv("AI_MODEL")
GITHUB_API_URL = "https://api.github.com"

global PR_SUMMARY, SEMGREP_FINDINGS, FILES_CONTENT, CHANGE_ANALYSIS, PR_DIFFS, PR_DIFF_FILES
PR_SUMMARY = ""
SEMGREP_FINDINGS = []
FILES_CONTENT = dict()
CHANGE_ANALYSIS = ""
PR_DIFFS = ""
PR_DIFF_FILES = dict()

def parse_git_diff(diff_text):
    """
    Parses a Git diff string and returns a dictionary mapping filenames to their respective diffs.
    
    Args:
        diff_text (str): The raw Git diff string.
    
    Returns:
        dict: A dictionary where keys are filenames and values are their respective diffs.
    """
    file_diffs = {}
    current_file = None
    diff_lines = []

    # Regex to match file changes in the diff format
    file_change_pattern = re.compile(r"^diff --git a\/(.+?) b\/(.+)$")

    for line in diff_text.splitlines():
        match = file_change_pattern.match(line)
        if match:
            # Store the previous file diff if one exists
            if current_file and diff_lines:
                file_diffs[current_file] = "\n".join(diff_lines)
            
            # Start tracking a new file
            current_file = match.group(2)  # Capture the filename after 'b/'
            diff_lines = [line]  # Start collecting lines for this file
        elif current_file:
            diff_lines.append(line)

    # Store the last collected diff
    if current_file and diff_lines:
        file_diffs[current_file] = "\n".join(diff_lines)
    return file_diffs

def get_pr_diff():
    """Fetch the full PR diff using the GitHub API."""
    global PR_DIFF_FILES, PR_DIFFS
    github_token = os.getenv('GITHUB_TOKEN')
    pr_number = os.getenv("PR_NUMBER")
    repo_name = os.getenv("REPO_NAME")
    diff_url = f"{GITHUB_API_URL}/repos/{repo_name}/pulls/{pr_number}"
    headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github.diff"  # Request raw diff format
    }

    response = requests.get(diff_url, headers=headers)

    if response.status_code != 200:
        print(f"Failed to fetch PR diff: {response.text}")
        return None

    PR_DIFFS = response.text
    PR_DIFF_FILES = parse_git_diff(response.text)
    return response.text 

def run_semgrep(files):
    """Runs Semgrep on the given files and returns findings."""
    semgrep_results = []
    
    console.print("\n[cyan]Running Semgrep security scan...\n")
    try:
        cmd = f"semgrep --config=auto --json {' '.join(files)}"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        # print(result.stdout)
        if result.returncode == 0 and result.stdout:
            semgrep_output = json.loads(result.stdout)
            for finding in semgrep_output.get("results", []):
                semgrep_results.append({
                    "file": finding["path"],
                    "rule": finding["check_id"],
                    "message": finding["extra"]["message"]
                })
    
    except Exception as e:
        console.print(f"[red]Error running Semgrep: {e}")
    
    return semgrep_results


def select_important_files(changed_files, max_files=5):
    """Select the most important files for analysis based on changes and file type"""
    # Prioritize files with most changes
    sorted_files = sorted(changed_files, key=lambda f: f.additions + f.deletions, reverse=True)
    
    # Further prioritize code files over non-code files
    code_extensions = ['.py', '.js', '.jsx', '.ts', '.tsx', '.java', '.c', '.cpp', '.cs', '.go', '.rb']
    
    code_files = [f for f in sorted_files if any(f.filename.endswith(ext) for ext in code_extensions)]
    other_files = [f for f in sorted_files if f not in code_files]
    
    # Combine lists, prioritizing code files
    important_files = code_files + other_files
    
    return important_files[:max_files]
    
def get_pr_context(url: str) -> dict:
    """Get PR details from GitHub"""
    gh = Github(os.getenv('GITHUB_TOKEN'))
    pattern = r"https://github\.com/([^/]+)/([^/]+)/pull/(\d+)"
    match = re.match(pattern, url)
    
    if not match:
        raise ValueError("Invalid GitHub PR URL")
        
    owner, repo, pr_number = match.groups()
    repo = gh.get_repo(f"{owner}/{repo}")
    pr = repo.get_pull(int(pr_number))
    
    return {
        'title': pr.title,
        'description': pr.body,
        'changed_files': list(pr.get_files()),
        'commits': list(pr.get_commits()),
        'status': pr.state,
        
    }

def get_file_contents(changed_files, pr_url):
    """Fetch content of changed files to provide more context to the LLM"""
    repo, pr_number = extract_repo_and_pr(pr_url)
    if not repo or not pr_number:
        return ""
    
    _, head_repo, head_branch = get_pr_details(repo, pr_number)
    
    # Select important files (limit to avoid overwhelming context)
    important_files = select_important_files(changed_files, max_files=10)
    
    file_contents = []
    for file in important_files:
        url = f"https://raw.githubusercontent.com/{head_repo}/refs/heads/{head_branch}/{file.filename}"
        response = requests.get(url)
        
        if response.status_code == 200:
            content = response.text
            
            file_contents.append(f"File: {file.filename}\n```\n{content}\n```\n")
    
            FILES_CONTENT[file.filename] = content
    return  "\n".join(file_contents)

def handle_token_limit(text, max_tokens=400000):
    """Trim the text to fit within the token limit."""
    return text[:max_tokens]

def determine_pr_type(title, description):
    """Classify PR type based on title and description."""
    keywords = {
        "bug": ["fix", "bug", "error", "issue", "patch"],
        "feature": ["add", "feature", "implement", "new"],
        "refactor": ["refactor", "cleanup", "restructure"],
        "security": ["security", "vulnerability", "CVE", "exploit"]
    }
    
    title_lower = title.lower()
    if description:
        desc_lower = description.lower()
    else:
        desc_lower = ""
    
    for pr_type, words in keywords.items():
        if any(word in title_lower or word in desc_lower for word in words):
            return pr_type
    
    return "general"

def generate_custom_prompt(pr_type, pr_context, files_content):
    """Generate a prompt tailored to the PR type."""
    base_prompt = f"""You are PR-Reviewer, a language model designed to review a Git Pull Request (PR).
    Summarize the following PR changes concisely:
    Title: {pr_context['title']}
    Description: {pr_context['description']}
    Changed File Contents:
    {files_content}
    File Diffs:
    {PR_DIFFS}
    If any of these are breaking only Then, your summary should include a note about alterations to the signatures of exported functions, global data structures and variables, and any changes that might affect the external interface or behavior of the code.
    Important:
    - In your summary do not mention that the file needs a through review or caution about potential issues.
    """

    prompts = {
        "bug": f"{base_prompt}\nExplain the root cause of this bug and assess the effectiveness of the fix.",
        "feature": f"{base_prompt}\nEvaluate the impact of this feature on existing functionality and suggest improvements.",
        "refactor": f"{base_prompt}\nAnalyze whether this refactoring improves maintainability and performance.",
        "security": f"{base_prompt}\nAssess whether this patch effectively mitigates the security issue.",
        "general": f"{base_prompt}"
    }
    
    ending = """\nRespond in the following way:
    Include the summary of the overall changes in three to four sentences.
    eg:  This PR addresses a bug where the user login was failing due to an incorrect API endpoint. The fix updates the endpoint URL in the authentication service. Additionally, a new feature was added to display user profile pictures. The feature introduces a new image processing library and updates the user profile component to fetch and display the image.
    \n
    """
    return prompts.get(pr_type, prompts["general"]) + ending

def generate_pr_summary(url):
    """Generates a PR summary using Ollama's CodeLlama model."""
    global PR_SUMMARY
    console.print("\n[cyan]Generating PR summary using AI...\n")
    pr_context = get_pr_context(url)
    
    files_content = get_file_contents(pr_context['changed_files'], url)
    
    # prompt = f"""You are PR-Reviewer, a language model designed to review a Git Pull Request (PR).
    # Summarize the following PR changes concisely:
    # Title: {pr_context['title']}
    # Description: {pr_context['description']}
    # Changed Files and Contents:
    # {files_content}
    # Provide a clear and concise summary of the content changes.
    # If applicable, your summary should include a note about alterations to the signatures of exported functions, global data structures and variables, and any changes that might affect the external interface or behavior of the code.
    # """
    # prompt = handle_token_limit(prompt)

    pr_type = determine_pr_type(pr_context["title"], pr_context["description"])
    prompt = generate_custom_prompt(pr_type, pr_context, files_content)
    prompt = handle_token_limit(prompt)
    
    
    payload = {"model": MODEL_NAME, "prompt": prompt, "stream": False}
    response = requests.post(OLLAMA_API_URL, json=payload)
    
    if response.status_code == 200:
        result = response.json()
        PR_SUMMARY = result.get("response", "[Error generating summary]")
        console.print(f"\n[green]PR Summary:\n{PR_SUMMARY}\n")
    else:
        console.print(f"[red]Error: {response.status_code} - {response.text}")

def analyze_change_impact(url):
    """Analyzes the impact of PR changes in depth."""
    global SEMGREP_FINDINGS, CHANGE_ANALYSIS
    console.print("\n[cyan]Analyzing PR Change Impact...\n")
    pr_context = get_pr_context(url)
    idx = 0
    for file in pr_context['changed_files']:
        idx += 1
        findings = [f for f in SEMGREP_FINDINGS if f['file'] == file.filename]
        #file_analysis = f"""File: {file.filename}\nChanges: +{file.additions}/-{file.deletions}\nFindings: {findings}\n"""
        changes = f"+{file.additions}/-{file.deletions}"
        if file.filename in FILES_CONTENT:
            changes = FILES_CONTENT[file.filename]
        curr_change = PR_DIFF_FILES[file.filename]
        file_analysis = f"""File: {file.filename}\nChanged File {changes}\nChanges between original and new content: {curr_change}\n\nSemgrep Findings: {findings}\n"""
        prompt = f"""You are PR-Reviewer, a language model designed to review a Git Pull Request (PR).
        Analyze the impact of changes in this PR file:
        Each change starts with diff --git a/{file.filename} b/{file.filename} indicating the file being modified.
        The index line shows file version hashes before and after the change.
        Lines beginning with --- and +++ indicate the file's previous and new versions.
        Added lines are prefixed with + (new content).
        Removed lines are prefixed with - (deleted content).
        Contextual lines (unchanged) have no prefix and help provide surrounding context.
        If a file is new, it starts with new file mode, and if deleted, it starts with deleted file mode.
        
        {file_analysis}
        
        How do these changes affect the overall project and code quality? Explain in 2-3 sentences atmost.
        Analysis Guidelines:

        For Configuration & Workflow Changes (.yml, .json, etc.):
            1. Identify what settings or dependencies have changed.
            2. Assess if the change introduces compatibility issues or risks.
        For Code Changes (.py, .js, .html, etc.):
            1. Analyze function modifications, new feature additions, or deletions without displaying the changes verbatim.
            2. Determine if the change affects existing logic or what is the intended effect of the new code or introduces new dependencies.
        For New Files:
            1. Describe the purpose of the new file.
            2. Consider how it integrates with the existing codebase.

        Important:
        Do NOT mention that the file needs a through review or that it is dfficult to without further context.
        Mention any other important information that might help the reviewer (eg: catching bugs or improve test coverage)
        The factors for good code are:
        Clarity, Correctness, Modular, Failure Handling, Security and analyzing blast radius.
        Identify any inconsistencies and highlight the lines numbers where this happens.

        Sample output format:
        Changes in this file modify the authentication service configuration, updating API endpoint URLs. This ensures the service connects to the correct resources. 
        The update could affect existing login functionality if not deployed correctly, but appears to correct a previous bug.
        Ensure proper testing is in place.
        """
        prompt = handle_token_limit(prompt)
        
        payload = {"model": MODEL_NAME, "prompt": prompt, "stream": False}
        response = requests.post(OLLAMA_API_URL, json=payload)
        
        if response.status_code == 200:
            result = response.json()
            CHANGE_ANALYSIS += f"\n{idx}. **Impact Analysis for `{file.filename}`**:\n\t{result.get('response', '[Error]')}\n"
            console.print(f"\n[green]Impact Analysis for {file.filename}:\n{result.get('response', '[Error]')}\n")
        else:
            console.print(f"[red]Error analyzing {file.filename}: {response.status_code} - {response.text}")

def extract_repo_and_pr(url):
    """Extracts the repo owner/name and PR number from a GitHub PR URL."""
    match = re.search(r"github\.com/([^/]+/[^/]+)/pull/(\d+)", url)
    if match:
        return match.group(1), match.group(2)
    else:
        console.print("[red]Invalid PR URL. Please provide a valid GitHub PR URL.")
        return None, None

def get_pr_details(repo, pr_number):
    """Fetches the PR details including changed files, head repo, and head branch."""
    cmd = f'gh pr view {pr_number} --repo {repo} --json files,headRefName,headRepository,headRepositoryOwner,isCrossRepository'
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

    if result.returncode != 0:
        console.print(f"[red]Error fetching PR details: {result.stderr}")
        exit(1)

    data = json.loads(result.stdout)
    files = [file["path"] for file in data.get("files", [])]
    head_branch = data.get("headRefName")
    is_forked = data.get("isCrossRepository")
    head_repo = data.get("headRepository", {}).get("name")
    owner = data.get("headRepositoryOwner", {}).get("login")

    if is_forked:
        return files, owner+"/"+head_repo, head_branch
    return files, repo, head_branch

def run_lint(pr_url):
    """Runs linters and Semgrep for all supported languages."""
    repo, pr_number = extract_repo_and_pr(pr_url)
    if not repo or not pr_number:
        return

    console.print(f"\n[orange]Fetching details for PR #{pr_number} from {repo}...\n")
    python_files, head_repo, head_branch = get_pr_details(repo, pr_number)

    if not python_files:
        console.print("[yellow]No valid files changed in this PR.")
        return

    console.print(f"[orange]Fetching files from forked repo: {head_repo}, branch: {head_branch}\n")
    temp_dir = "./downloaded_code"
    try:
        os.mkdir("downloaded_code") #tempfile.mkdtemp()  # Persistent temp dir until user exits PR analysis
    except Exception:
        pass

    downloaded_files = download_files(temp_dir, head_repo, python_files, head_branch)
    console.print("\n[cyan]Running static code analysis...\n")
    global SEMGREP_FINDINGS
    SEMGREP_FINDINGS = run_semgrep(downloaded_files)
    
    for file in downloaded_files:
        if file.endswith(".py"):
            console.print(f"[blue]Running pylint for {file}...")
            cmd = f"pylint {file}"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            console.print(f"[cyan]{result.stdout}")

        elif file.endswith((".js", ".jsx", ".ts", ".tsx")):
            if file == "package.json":
                continue
            console.print(f"[blue]Running eslint for {file}...")
            cmd = f"npx eslint {file}"
            result = subprocess.run(cmd, shell=True, cwd=os.path.dirname(file), capture_output=True, text=True)
            if result.stderr or not result.stdout:
                console.print(f"[cyan]No issues found..")
            else:
                console.print(f"[cyan]{result.stdout}")
        
        else:
            console.print(f"[yellow]No linter configured for {file}")

def download_files(temp_dir, repo, files, branch):
    """Downloads files to a temporary directory for analysis with progress bar."""
    downloaded_files = []
    
    with Progress() as progress:
        task = progress.add_task("[cyan]Downloading files...", total=len(files))
        
        for file_path in files:
            url = f"https://raw.githubusercontent.com/{repo}/refs/heads/{branch}/{file_path}"
            print(url)
            response = requests.get(url)

            if response.status_code == 200:
                local_path = os.path.join(temp_dir, os.path.basename(file_path))
                with open(local_path, "w", encoding="utf-8") as f:
                    f.write(response.text)
                downloaded_files.append(local_path)
                progress.advance(task)
                console.print(f"[green]Downloaded: {file_path}")
            else:
                console.print(f"[red]Failed to download {file_path} (Repo: {repo}, Branch: {branch})")
    
    return downloaded_files

def post_comment_on_pr(pr_url, comment, file_name):
    """Posts a comment on the PR with analysis results."""
    gh = Github(os.getenv('GITHUB_TOKEN'))
    owner, repo, pr_number = re.search(r"github\.com/([^/]+)/([^/]+)/pull/(\d+)", pr_url).groups()

    repo = gh.get_repo(f"{owner}/{repo}")
    pr = repo.get_pull(int(pr_number))
    pr.create_issue_comment(comment)
    with open(file_name, "w") as f:
        f.write(comment)
    console.print(f"[green]Posted analysis comment on PR #{pr_number}")

def review_file_content(pr, file_name, file_content, diff_content):
    """
    Review a specific file's content and provide line-by-line comments.
    
    Args:
        file_name (str): Name of the file being reviewed
        file_content (str): Content of the file
        diff_content (str): Git diff content for this file
    
    Returns:
        list: A list of dictionaries containing line numbers and review comments
    """
    global PR_DIFF_FILES
    console.print(f"\n[cyan]Reviewing file content for {file_name}...\n")
    
    # Parse diff to understand which lines were changed
    changed_lines = parse_changed_lines(diff_content)
    
    # Prepare the file content with line numbers for context
    file_lines = file_content.splitlines()
    file_with_lines = "\n".join([f"{i+1}: {line}" for i, line in enumerate(file_lines)])
    
    # Create a prompt that focuses on code quality issues
    prompt = f"""You are PR-Reviewer, a language model skilled at detailed code review.
    
    Review the following file and provide specific line-by-line comments **ONLY WHERE ISSUES EXIST**.

    File: {file_name}
    
    ```
    {file_with_lines}
    ```
    
    Changed lines (line numbers): {', '.join(map(str, changed_lines))}
    
    Analyze ONLY the changed lines and provide specific feedback on:
    1. Code correctness and suggestions for optimal code (eg: space and time complexity) and logic issues
    2. Security vulnerabilities
    3. Performance concerns
    4. Style and readability issues
    5. Potential bugs or edge cases
    
    For each issue, provide:
    1. The exact line number
    2. A concise description of the issue
    3. A specific suggestion for improvement
    
    Format your response as a JSON list of objects like:
    [
        {{"line": 42, "comment": "This variable is never used. Consider removing it or documenting why it's needed."}},
        {{"line": 87, "comment": "This loop could be optimized by using a set instead of a list for lookups."}}
    ]
    
    Only include comments for lines with actual issues - don't comment on every line.
    If no issues are found, return an empty list.
    RESPOND ONLY WITH THE JSON LIST.
    """
    
    print(prompt)
    payload = {"model": MODEL_NAME, "prompt": prompt, "stream": False}
    response = requests.post(OLLAMA_API_URL, json=payload)
    
    review_comments = []
    if response.status_code == 200:
        result = response.json().get("response", "[]")
        try:
            # Extract the JSON part from the response
            json_str = result
            if not json_str.startswith('['):
                # If the model included any preamble text, try to find the JSON list
                json_start = result.find('[')
                json_end = result.rfind(']') + 1
                if json_start >= 0 and json_end > json_start:
                    json_str = result[json_start:json_end]
            
            review_comments = json.loads(json_str)
            console.print(review_comments)
            console.print(f"[green]Found {len(review_comments)} issues in {file_name}")
        except json.JSONDecodeError as e:
            console.print(f"[red]Error parsing review comments: {e}")
            console.print(f"[red]Raw response: {result}")
    else:
        console.print(f"[red]Error reviewing {file_name}: {response.status_code} - {response.text}")
    
    return review_comments

def parse_changed_lines(diff_content):
    """
    Parse a Git diff to extract line numbers that were changed.
    
    Args:
        diff_content (str): The Git diff content for a file
    
    Returns:
        list: List of line numbers that were changed (added or modified)
    """
    changed_lines = []
    current_line = 0
    
    for line in diff_content.splitlines():
        if line.startswith("@@"):
            # Parse the @@ line to get the starting line number in the new file
            # Format is typically: @@ -old_start,old_count +new_start,new_count @@
            match = re.search(r"\+(\d+)", line)
            if match:
                current_line = int(match.group(1)) - 1  # -1 because we increment before using
        elif line.startswith("+") and not line.startswith("+++"):
            # This is an added/modified line (not the +++ filename line)
            current_line += 1
            changed_lines.append(current_line)
        elif not line.startswith("-"):
            # This is a context line (not removed)
            current_line += 1
    
    return changed_lines

def post_line_comments(pr_url, file_reviews):
    """
    Post review comments on specific lines of files in the PR.
    
    Args:
        pr_url (str): URL of the PR
        file_reviews (dict): Dictionary mapping filenames to lists of review comments
    """
    gh = Github(os.getenv('GITHUB_TOKEN'))
    owner, repo, pr_number = re.search(r"github\.com/([^/]+)/([^/]+)/pull/(\d+)", pr_url).groups()
    
    repo = gh.get_repo(f"{owner}/{repo}")
    pr = repo.get_pull(int(pr_number))
    
    # Get the latest commit in the PR
    latest_commit = list(pr.get_commits())[-1]
    comment_count = 0

    for file_name, comments in file_reviews.items():
        for comment in comments:
            try:
                cm = pr.create_review_comment(
                    body=comment["comment"],
                    commit=latest_commit,
                    path=file_name,
                    line=int(comment["line"]),
                    as_suggestion=False
                )
                comment_count += 1
                console.print(f"[green]Posted comment on {file_name}: {cm}")
            except Exception as e:
                console.print(f"[red]Error posting comment to {file_name}:: {e}")

    
    console.print(f"[green]Posted {comment_count} line-specific comments on the PR")

def review_all_files(pr_url):
    """Review all changed files in the PR and post line-specific comments."""
    global PR_DIFF_FILES, FILES_CONTENT
    
    console.print("\n[cyan]Starting detailed file review...\n")
    
    file_reviews = {}
    pr = Github(os.getenv('GITHUB_TOKEN')).get_repo("/".join(extract_repo_and_pr(pr_url)[0].split("/"))).get_pull(int(extract_repo_and_pr(pr_url)[1]))
    f = ""
    # Review each file that has content available
    for file_name, file_content in FILES_CONTENT.items():
        if file_name in PR_DIFF_FILES:
            f = file_name
            diff_content = PR_DIFF_FILES[file_name]
            review_comments = review_file_content(pr, file_name, file_content, diff_content)
            
            if review_comments:
                file_reviews[file_name] = review_comments
    
    # Post comments on the PR
    if file_reviews:
        post_line_comments(pr_url, file_reviews)
        
        # Also save the reviews to a file
        # with open("line_reviews.json", "w") as f:
        #     json.dump(file_reviews, f, indent=2)
        
        # # Generate a summary comment for the PR
        # total_comments = sum(len(comments) for comments in file_reviews.values())
        # summary = f"## AI PR Line-by-Line Review\n\n"
        # summary += f"Found {total_comments} issues across {len(file_reviews)} files.\n\n"
        
        # for file_name, comments in file_reviews.items():
        #     summary += f"### {file_name}\n"
        #     for comment in comments:
        #         summary += f"- Line {comment['line']}: {comment['comment']}\n"
        #     summary += "\n"
        
        # pr.create_issue_comment(summary)
    else:
        console.print("[yellow]No issues found in the detailed file review.")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--pr-url":
        pr_url = sys.argv[2]
        console.print(f"[cyan]Running PR analysis for {pr_url}...\n")
        get_pr_diff()
        
        generate_pr_summary(pr_url)
        pr_comment = f"## AI PR Review Summary\n\n**Summary:**\n{PR_SUMMARY}\n"
        post_comment_on_pr(pr_url, pr_comment, "pr_summary.txt")
        
        # analyze_change_impact(pr_url)
        # pr_change_analysis = f"## AI PR Review File Change Analysis\n\n**Description:**\n{CHANGE_ANALYSIS}\n"
        # post_comment_on_pr(pr_url, pr_change_analysis, "pr_analysis.txt")
        review_all_files(pr_url)
    else:
        console.print("[red]Missing PR URL. Run the script with `--pr-url <PR_URL>`")
