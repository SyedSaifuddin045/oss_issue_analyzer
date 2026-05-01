# OSS Issue Analyzer

A CLI tool that helps first-time open source contributors analyze GitHub issues against their local cloned repositories. It indexes code plus selected project text assets, estimates difficulty using AI or heuristics, and helps contributors pick issues they can realistically solve.

## Features

- **Mixed Repository Indexing** - Parse code and index selected config, workflow, and documentation files
- **GitHub Issue Integration** - Fetch issues directly from GitHub
- **Bulk Issue Scanning** - Quick heuristic scoring (~80% accurate) for ALL issues using parallel processing
- **AI-Powered Scoring** - Supports multiple LLM providers (OpenAI, Anthropic, Google, Azure OpenAI) for intelligent difficulty estimation and suggestions
- **Heuristic Fallback** - Rule-based scoring when AI is unavailable
- **Hybrid Retrieval** - Semantic + keyword search against indexed code
- **Contributing Signals** - Identifies test files, documentation, and isolated changes
- **Issue Comments Context** - Includes GitHub issue comments (prioritized by maintainer input and popularity) to understand expected practices
- **Smart Caching** - Minimizes API calls and costs (98% reduction in AI costs)

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

# 3. Bulk scan issues (FREE - uses quick heuristics)
oss-issue-analyzer list-issues

# 4. Deep analyze selected issue (1 AI call only)
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

### 3. List and Analyze Issues (Bulk Scan)

Scan ALL open issues with quick heuristic scoring (FREE, ~80% accurate), then deep-analyze only the ones you're interested in:

```bash
# Bulk scan (uses quick heuristics, NO AI calls)
oss-issue-analyzer list-issues

# Filter and sort
oss-issue-analyzer list-issues --filter-difficulty easy
oss-issue-analyzer list-issues --sort difficulty
oss-issue-analyzer list-issues --filter-label "good first issue"

# Interactive mode (select and analyze immediately)
oss-issue-analyzer list-issues --interactive

# Deep analysis (1 AI call for selected issue)
oss-issue-analyzer analyze 123
```

**Cost Comparison:**
| Approach | GitHub API Calls | AI API Calls | Cost |
|-----------|-------------------|-----------------|------|
| Analyze each issue | 50 + comments | 50 | $$$ |
| **Bulk scan + select** | 1-2 + 1 (selected) | **1** | **$** |

**Options:**
```bash
oss-issue-analyzer list-issues [OPTIONS]

Options:
  --repo OWNER/REPO       # GitHub repo (auto-detected from git)
  --state open|all|closed  # Filter by state [default: open]
  --sort difficulty|number|created  # Sort results
  --filter-difficulty easy|medium|hard
  --filter-label TEXT      # e.g., "good first issue"
  --limit N                 # Max issues to show [default: 0=all]
  --cache-ttl HOURS        # Cache duration [default: 1]
  --no-cache                # Force re-fetch
  --workers N              # Parallel workers [default: auto]
  --json                   # JSON output
  --interactive            # Select and analyze immediately
```

**Output Example:**
```
╭────── List of Issues (repo: owner/repo, 47 open) ──────╮
│ #    Title                    Difficulty  Conf    Labels          │
│ 123  Fix parser crash         EASY       82%      good-first-issue │
│ 124  Add new feature          HARD       75%      enhancement      │
│ 125  Update README            EASY       90%      docs             │
└───────────────────────────────────────────────────────────────────────╯

Tip: Run 'oss-issue-analyzer analyze <number>' for detailed AI analysis
```

### 4. Analyze an Issue

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

### 5. Use Local Issue File

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
5. **Falls back to heuristics** if AI is unavailable

**Without AI**, the tool uses rule-based heuristics to estimate difficulty based on code complexity, file types, and metadata.

## Output Example

### AI-Powered Analysis
```
╭─────────────── Issue: Fix tokenizer performance ────────────────╮
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
╭─────────────── Issue: Fix tokenizer performance ────────────────╮
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

### Cache Storage

Analysis results are cached in `.oss-issue-analyzer-cache/` in the repository root:
- `issues/` - Issue lists with quick scores (fresh for 1 hour by default)
- `analysis/` - Full AI analysis for individual issues (cached indefinitely)

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run all tests
pytest

# Run specific test files
pytest tests/test_quick_scorer.py
pytest tests/test_cache.py
pytest tests/test_bulk_processor.py
pytest tests/test_ai_scorer.py
```

## License

MIT
