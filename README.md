# OSS Issue Analyzer

A CLI tool that helps first-time open source contributors analyze GitHub issues against their local cloned repositories. It indexes code plus selected project text assets, estimates difficulty using AI or heuristics, and helps contributors pick issues they can realistically solve.

## Features

- **Mixed Repository Indexing** - Parse code and index selected config, workflow, and documentation files
- **GitHub Issue Integration** - Fetch issues directly from GitHub
- **AI-Powered Scoring** - Supports multiple LLM providers (OpenAI, Anthropic, Google, Azure OpenAI) for intelligent difficulty estimation and suggestions
- **Heuristic Fallback** - Rule-based scoring when AI is unavailable
- **Hybrid Retrieval** - Semantic + keyword search against indexed code
- **Contributing Signals** - Identifies test files, documentation, and isolated changes
- **Issue Comments Context** - Includes GitHub issue comments (prioritized by maintainer input and popularity) to understand expected practices

## Installation

```bash
pip install oss-issue-analyzer
```

Or install in development mode:

```bash
pip install -e .
```

## Quick Start

```bash
# 1. Index your repository
cd /path/to/repo
oss-issue-analyzer index .

# 2. (Optional) Set up AI provider for smarter analysis
oss-issue-analyzer setup

# 3. Analyze an issue
oss-issue-analyzer analyze 123
```

## Usage

### 1. Index a Repository

```bash
cd /path/to/repo
oss-issue-analyzer index .
```

This creates a `.oss-index/` folder in the repository root containing vector embeddings for code and selected project text assets.

**Options:**
```bash
oss-issue-analyzer index <repo_path> [OPTIONS]

Options:
  --embedder    Embedding model (nomic, minilm) [default: minilm]
  --index-mode  Index mode (mixed, code-only) [default: mixed]
  --force        Force re-index from scratch
```

### 2. Set Up AI Provider (Optional but Recommended)

Configure an AI provider to get smarter difficulty analysis and suggestions:

```bash
# List available providers based on your .env
oss-issue-analyzer setup --list

# Interactive setup
oss-issue-analyzer setup

# Direct setup with provider and API key
oss-issue-analyzer setup --provider openai --api-key sk-... --test

# Clear saved configuration
oss-issue-analyzer setup --clear
```

**Supported Providers:**
| Provider | Environment Variable | Default Model |
|----------|----------------------|---------------|
| OpenAI | `OPENAI_API_KEY` | gpt-4o-mini |
| Anthropic (Claude) | `ANTHROPIC_API_KEY` | claude-3-haiku-20240307 |
| Google (Gemini) | `GOOGLE_API_KEY` | gemini-1.5-flash |
| Azure OpenAI | `AZURE_OPENAI_API_KEY` + `AZURE_OPENAI_ENDPOINT` | (deployment name) |

### 3. Analyze an Issue

```bash
# Using issue number (run from the cloned repo directory)
oss-issue-analyzer analyze 123

# Using a GitHub URL
oss-issue-analyzer analyze https://github.com/owner/repo/issues/123

# Force AI provider
oss-issue-analyzer analyze 123 --ai-provider openai

# Disable AI and use heuristics only
oss-issue-analyzer analyze 123 --no-ai
```

The tool automatically detects the GitHub remote from the local git repository.

**Options:**
```bash
oss-issue-analyzer analyze <issue_ref> [OPTIONS]

Arguments:
  issue_ref        Issue number, URL, or path to local markdown file

Options:
  --repo           Path to indexed repository
  --db-path        Path to index database
  --embedder       Embedding model [default: minilm]
  --limit           Number of indexed units to retrieve [default: 10]
  --gh-repo         GitHub repo (owner/repo) - auto-detected if not provided
  --ai-provider     AI provider to use (openai, anthropic, google, azure_openai)
  --no-ai          Disable AI scoring, use heuristics only
```

### 4. Use Local Issue File

```bash
oss-issue-analyzer analyze ./issue.md
```

The markdown file should start with a `# Title` heading.

## How AI Scoring Works

When an AI provider is configured, the tool:

1. **Fetches GitHub issue comments** (up to 7, prioritized by maintainer input and reaction count)
2. **Retrieves relevant code units** using hybrid search (semantic + keyword)
3. **Builds a context-rich prompt** including:
   - Issue title, body, type, and error patterns
   - GitHub issue comments with community/maintainer insights
   - Retrieved code units with signatures and docstrings
   - Heuristic scoring results for reference
4. **Sends to LLM** for intelligent analysis
5. **Falls back to heuristics** if AI is unavailable or fails

**Without AI**, the tool uses rule-based heuristics to estimate difficulty based on code complexity, file types, and metadata.

## Output Example

### AI-Powered Analysis
```
╭─────────────── Issue: Fix tokenizer performance ───────────────╮
│ Difficulty: EASY (conf: 88%) [AI]                            │
│ Relative: Easier than 75%                                      │
│                                                                │
│ Relevant files:                                                │
│   → src/tokenizer.py                                           │
│   → tests/test_tokenizer.py                                    │
│                                                                │
│ Suggested approach:                                            │
│   1. Start in src/tokenizer.py -> Tokenizer.encode             │
│   2. The batch processing logic needs optimization               │
│   3. Test: pytest tests/test_tokenizer.py                      │
│                                                                │
│ Contributor signals:                                           │
│  > Test file exists - changes are verifiable                   │
│  > Has documentation                                           │
│  > Isolated change possible                                    │
└────────────────────────────────────────────────────────────────╯
```

### Heuristic Analysis (No AI)
```
╭─────────────── Issue: Fix tokenizer performance ───────────────╮
│ Difficulty: EASY (conf: 88%)                                   │
│ Relative: Easier than 75%                                      │
│                                                                │
│ Relevant files:                                                │
│   → src/tokenizer.py                                           │
│   → tests/test_tokenizer.py                                    │
│                                                                │
│ Suggested approach:                                            │
│   1. Start in src/tokenizer.py -> Tokenizer.encode             │
│   2. Bug is in the batch processing logic                      │
│   3. Test: pytest tests/test_tokenizer.py                      │
│                                                                │
│ Contributor signals:                                           │
│  > Test file exists - changes are verifiable                   │
│  > Has documentation                                           │
│  > Isolated change possible                                    │
└────────────────────────────────────────────────────────────────╯
```

## Configuration

### Environment Variables

Create a `.env` file in your project root (see `.env.example` for template):

| Variable | Description |
|----------|-------------|
| `GITHUB_TOKEN` | GitHub personal access token for API rate limits |
| `HF_TOKEN` | Hugging Face token for faster embedding downloads |
| `OPENAI_API_KEY` | OpenAI API key |
| `OPENAI_MODEL` | OpenAI model (default: gpt-4o-mini) |
| `ANTHROPIC_API_KEY` | Anthropic API key |
| `ANTHROPIC_MODEL` | Anthropic model (default: claude-3-haiku-20240307) |
| `GOOGLE_API_KEY` | Google Gemini API key |
| `AZURE_OPENAI_API_KEY` | Azure OpenAI API key |
| `AZURE_OPENAI_ENDPOINT` | Azure OpenAI endpoint URL |
| `AZURE_OPENAI_DEPLOYMENT` | Azure OpenAI deployment name |
| `AI_ENABLED` | Enable/disable AI scoring (true/false) |
| `AI_TIMEOUT_SECONDS` | AI request timeout (default: 30) |

### Configuration File

Provider preferences are saved to `~/.config/oss-issue-analyzer/config.json`.

### Data Storage

Index data is stored in `.oss-index/` folder in the repository root:
- `index.lance/code_units.lance` - Vector embeddings
- `index.lance/repositories.lance` - Repository metadata

If you indexed a repository with an older version of the tool, re-run:

```bash
oss-issue-analyzer index . --force
```

The mixed index adds schema metadata and stores non-code assets alongside code units.

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run specific test files
pytest tests/test_ai_scorer.py
pytest tests/test_github_client.py
pytest tests/test_llm_provider.py
```

## License

MIT
