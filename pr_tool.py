import os
import subprocess
import json
import requests
import re
import shutil
from github import Github
from rich.console import Console
from rich.progress import Progress

console = Console()
OLLAMA_API_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "codellama"

global PR_SUMMARY, SEMGREP_FINDINGS
PR_SUMMARY = ""
SEMGREP_FINDINGS = []
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
        'status': pr.state
    }

def handle_token_limit(text, max_tokens=4000):
    """Trim the text to fit within the token limit."""
    return text[:max_tokens]

def generate_pr_summary(url):
    """Generates a PR summary using Ollama's CodeLlama model."""
    global PR_SUMMARY
    console.print("\n[cyan]Generating PR summary using AI...\n")
    pr_context = get_pr_context(url)
    
    files_content = "\n".join([
        f"File: {f.filename}\nChanges: +{f.additions}/-{f.deletions}\n"
        for f in pr_context['changed_files']
    ])
    
    prompt = f"""Summarize the following PR changes concisely:
    Title: {pr_context['title']}
    Description: {pr_context['description']}
    Changed Files:
    {files_content}
    Provide a clear and concise summary of the changes.
    """
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
    global SEMGREP_FINDINGS
    console.print("\n[cyan]Analyzing PR Change Impact...\n")
    pr_context = get_pr_context(url)
    
    for file in pr_context['changed_files']:
        findings = [f for f in SEMGREP_FINDINGS if f['file'] == file.filename]
        file_analysis = f"""File: {file.filename}\nChanges: +{file.additions}/-{file.deletions}\nFindings: {findings}\n"""
        
        prompt = f"""Analyze the impact of changes in this PR file:
        {file_analysis}
        How do these changes affect the overall project and code quality?"""
        prompt = handle_token_limit(prompt)
        
        payload = {"model": MODEL_NAME, "prompt": prompt, "stream": False}
        response = requests.post(OLLAMA_API_URL, json=payload)
        
        if response.status_code == 200:
            result = response.json()
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

def post_comment_on_pr(pr_url, comment):
    """Posts a comment on the PR with analysis results."""
    gh = Github(os.getenv('GITHUB_TOKEN'))
    owner, repo, pr_number = re.search(r"github\.com/([^/]+)/([^/]+)/pull/(\d+)", pr_url).groups()

    repo = gh.get_repo(f"{owner}/{repo}")
    pr = repo.get_pull(int(pr_number))
    pr.create_issue_comment(comment)
    console.print(f"[green]Posted analysis comment on PR #{pr_number}")

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

        generate_pr_summary(pr_url)
        analyze_change_impact(pr_url)

        pr_comment = f"## AI PR Review Summary\n\n**Summary:**\n{PR_SUMMARY}\n\n**Semgrep Findings:**\n{json.dumps(SEMGREP_FINDINGS, indent=2)}"
        post_comment_on_pr(pr_url, pr_comment)
    else:
        console.print("[red]Missing PR URL. Run the script with `--pr-url <PR_URL>`")
