# AI PR Reviewer

An AI-powered Pull Request reviewer and chatbot that provides:
- Automated code reviews with inline comments
- A chatbot interface to discuss code changes 
- Security scanning with Semgrep

## Features

### PR Analysis
- Summarizes PR changes for quick understanding
- Performs in-depth code analysis on modified files
- Identifies potential bugs, security issues, and performance concerns
- Posts reviews as both summary comments and inline feedback

### Interactive Chatbot
- Chat about code changes directly in PR comments
- Ask questions about specific files or functionality
- Get explanations of complex parts of the PR
- Simply comment with `/ai` followed by your question

## How to Use

### PR Review
When a PR is opened or updated, the AI will automatically:
1. Generate a summary of changes
2. Review each modified file
3. Post review comments
4. Add a chatbot introduction comment

### Chatbot
To chat with the AI about the code changes:
1. Comment on the PR with `/ai` followed by your question
   - Example: `/ai What does the change in utils.py do?`
   - Example: `/ai Are there any performance concerns with this approach?` 
2. The AI will respond with a comment addressing your question

### Local Usage
```bash
# Install dependencies
pip install -r requirements.txt

# Run a review on a PR
python pr_tool.py --pr-url "https://github.com/owner/repo/pull/123"

# Start an interactive chat session about a PR
python pr_tool.py --pr-url "https://github.com/owner/repo/pull/123" --chat

# Monitor PR comments for chatbot commands
python pr_tool.py --pr-url "https://github.com/owner/repo/pull/123" --monitor
```

## Requirements
- Python 3.10+
- GitHub API token with PR access
- Ollama (for running the AI model locally)