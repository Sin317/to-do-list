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
                    "message": finding["extra"]["message"],
                    "start_line": finding["start"]["line"],
                    "end_line": finding["end"]["line"],
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

def generate_custom_prompt(pr_type, pr_context, files_content, filename, file_diff):
    """Generate a prompt tailored to the PR type and specific file."""
    base_prompt = f"""You are PR-Reviewer, a language model designed to review a Git Pull Request (PR).
    Analyze the changes in the following file: `{filename}`.
    PR Title: {pr_context['title']}
    PR Description: {pr_context['description']}
    File Content:
    ```
    {files_content.get(filename, 'No content available')}
    ```
    File Diff:
    ```diff
    {file_diff}
    ```
    Provide specific feedback on the changes in this file.
    Focus on clarity, correctness, potential issues, and adherence to best practices.
    Point out specific lines where improvements can be made.
    If any of these are breaking changes (alterations to the signatures of exported functions, global data structures and variables, or changes that might affect the external interface or behavior of the code), please mention them.
    """

    prompts = {
        "bug": f"{base_prompt}\nExplain if the changes effectively fix the bug and if any new issues are introduced.",
        "feature": f"{base_prompt}\nEvaluate how well the new feature is implemented and if it integrates well with the existing codebase. Suggest potential improvements.",
        "refactor": f"{base_prompt}\nAssess if the refactoring improves the code's maintainability, readability, and performance. Highlight any potential regressions.",
        "security": f"{base_prompt}\nAnalyze if the changes effectively address the security vulnerability and if any new security risks are introduced.",
        "general": f"{base_prompt}"
    }

    ending = """\nRespond with specific comments or suggestions related to the changes in this file. If you have a comment about a specific line, please indicate the line number(s).
    For example:
    - Line 25: Consider adding input validation to prevent potential errors.
    - The logic in this function seems complex; could it be simplified?
    - This change introduces a breaking change in the API; ensure documentation is updated.
    """
    return prompts.get(pr_type, prompts["general"]) + ending

def generate_file_analysis(url):
    """Generates file-by-file analysis using Ollama."""
    global PR_DIFF_FILES, FILES_CONTENT
    console.print("\n[cyan]Generating file-by-file analysis using AI...\n")
    pr_context = get_pr_context(url)
    pr_type = determine_pr_type(pr_context["title"], pr_context["description"])
    files_content = FILES_CONTENT  # Assuming FILES_CONTENT is already populated
    github_token = os.getenv('GITHUB_TOKEN')
    owner, repo_name, pr_number = re.search(r"github\.com/([^/]+)/([^/]+)/pull/(\d+)", url).groups()
    gh = Github(github_token)
    repo = gh.get_repo(f"{owner}/{repo_name}")
    pr = repo.get_pull(int(pr_number))

    for filename, diff in PR_DIFF_FILES.items():
        file_content = FILES_CONTENT.get(filename, '')
        prompt = generate_custom_prompt(pr_type, pr_context, files_content, filename, diff)
        prompt = handle_token_limit(prompt)

        payload = {"model": MODEL_NAME, "prompt": prompt, "stream": False}
        response = requests.post(OLLAMA_API_URL, json=payload)

        if response.status_code == 200:
            result = response.json()
            analysis = result.get("response", "[Error generating analysis for this file]")
            console.print(f"\n[green]Analysis for `{filename}`:\n{analysis}\n")
            post_comments_for_file(repo, pr, filename, diff, analysis)
        else:
            console.print(f"[red]Error analyzing `{filename}`: {response.status_code} - {response.text}")

def post_comments_for_file(repo, pull, filename, diff, analysis):
    """Posts comments on specific lines of the PR based on the analysis."""
    lines = diff.splitlines()
    comment_lines = {}
    for line in analysis.splitlines():
        match = re.search(r"Line (\d+): (.*)", line)
        if match:
            line_number = int(match.group(1))
            comment_text = match.group(2).strip()

            # Need to map the line number in the new file to the diff context
            new_file_line = 0
            original_line = 0
            in_hunk = False
            hunk_start_line = None

            for diff_line in lines:
                if diff_line.startswith("@@"):
                    in_hunk = True
                    hunk_info = diff_line.split("@@")[1].strip()
                    original_range, new_range = hunk_info.split(" ")
                    original_start = int(original_range.split(",")[0].replace("-", ""))
                    new_start = int(new_range.split(",")[0].replace("+", ""))
                    hunk_start_original = original_start
                    hunk_start_new = new_start
                    original_line = original_start -1 # Adjust for context lines
                    new_file_line = new_start - 1 # Adjust for context lines
                    continue
                elif in_hunk:
                    if diff_line.startswith("+"):
                        new_file_line += 1
                        if new_file_line == line_number:
                            if filename not in comment_lines:
                                comment_lines[filename] = []
                            comment_lines[filename].append((line_number, comment_text))
                            break
                    elif not diff_line.startswith("-"):
                        original_line += 1
                        new_file_line += 1
            elif re.search(r"The logic in this function seems complex", line):
                # Generic comment on the file
                pull.create_issue_comment(f"**AI Review for `{filename}`:**\n{line}")


    for file, comments in comment_lines.items():
        for line_num, comment in comments:
            try:
                pull.create_comment(body=f"**AI Suggestion:** {comment}", path=file, position=line_num)
                console.print(f"[blue]Comment posted on `{file}` at line {line_num}: {comment}")
            except Exception as e:
                console.print(f"[red]Error posting comment on `{file}` at line {line_num}: {e}")

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
    files_data = data.get("files", [])
    files = [file["path"] for file in files_data]
    head_branch = data.get("headRefName")
    is_forked = data.get("isCrossRepository")
    head_repo = data.get("headRepository", {}).get("name")
    owner = data.get("headRepositoryOwner", {}).get("login")

    changed_files_objects = []
    for file_info in files_data:
        changed_files_objects.append(type('ChangedFile', (), file_info)())

    if is_forked:
        return changed_files_objects, owner+"/"+head_repo, head_branch
    return changed_files_objects, repo, head_branch


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

def create_inline_comment(pr, file_path, line_number, comment_body):
    """Creates an inline comment on a specific line of code in a PR."""
    try:
        # Get the commit SHA of the PR's head
        commit_sha = pr.head.sha
        
        # Create the review comment
        pr.create_review_comment(
            body=comment_body,
            commit_id=commit_sha,
            path=file_path,
            line=line_number
        )
        console.print(f"[green]Posted inline comment on {file_path} line {line_number}")
    except Exception as e:
        console.print(f"[red]Error creating inline comment: {e}")

def main():
    """Interactive CLI to analyze PRs."""
    console.print("[bold magenta]AI PR Review Tool[/bold magenta]\n")

    # while True:
    #     console.print("\n1. Input PR URL")
    #     console.print("2. Generate PR Summary")
    #     console.print("3. Analyze Change Impact")
    #     console.print("4. Run Static Analysis")
    #     console.print("5. Exit")
    #     choice = input("Enter choice: ").strip()

    #     if choice == "1":
    #         pr_url = input("Enter GitHub PR URL: ").strip()
    #         # run_lint(pr_url)
    #     elif choice == "2":
    #         generate_pr_summary(pr_url)
    #         # console.print(f"\n[green]PR Summary:\n{PR_SUMMARY}")
    #     elif choice == "3":
    #         analyze_change_impact(pr_url)
    #     elif choice == "5":
    #         console.print("[green]Exiting...")
    #         break
    #     else:
    #         console.print("[yellow]Invalid choice. Try again.")



if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--pr-url":
        pr_url = sys.argv[2]
        console.print(f"[cyan]Running PR analysis for {pr_url}...\n")

        get_pr_diff()
        
        generate_pr_summary(pr_url)
        pr_comment = f"## AI PR Review Summary\n\n**Summary:**\n{PR_SUMMARY}\n"
        post_comment_on_pr(pr_url, pr_comment, "pr_summary.txt")
        
        analyze_change_impact(pr_url)
        pr_change_analysis = f"## AI PR Review File Change Analysis\n\n**Description:**\n{CHANGE_ANALYSIS}\n"
        post_comment_on_pr(pr_url, pr_change_analysis, "pr_analysis.txt")
    else:
        console.print("[red]Missing PR URL. Run the script with `--pr-url <PR_URL>`")
