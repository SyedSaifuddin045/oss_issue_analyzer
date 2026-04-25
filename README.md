# OSS Issue Analyzer

A CLI tool that helps first-time open source contributors analyze GitHub issues against their local cloned repositories. It indexes code plus selected project text assets, estimates difficulty, and helps contributors pick issues they can realistically solve.

## Features

- **Mixed Repository Indexing** - Parse code and index selected config, workflow, and documentation files
- **GitHub Issue Integration** - Fetch issues directly from GitHub
- **Difficulty Estimation** - Heuristic-based scoring for issue complexity
- **Hybrid Retrieval** - Semantic + keyword search against indexed code
- **Contributing Signals** - Identifies test files, documentation, and isolated changes

## Installation

```bash
pip install oss-issue-analyzer
```

Or install in development mode:

```bash
pip install -e .
```

## Usage

### 1. Index a Repository

```bash
cd /path/to/repo
oss-issue-analyzer index .
```

This creates a `.oss-index/` folder in the repository root containing vector embeddings for code and selected project text assets.

### 2. Analyze an Issue

```bash
# Using issue number (run from the cloned repo directory)
oss-issue-analyzer analyze 123

# Using a GitHub URL
oss-issue-analyzer analyze https://github.com/owner/repo/issues/123
```

The tool automatically detects the GitHub remote from the local git repository.

### 3. Use Local Issue File

```bash
oss-issue-analyzer analyze ./issue.md
```

## Commands

### `index`

Index a local repository for issue analysis.

```bash
oss-issue-analyzer index <repo_path> [OPTIONS]

Options:
  --embedder  Embedding model (nomic, minilm) [default: minilm]
  --index-mode  Index mode (mixed, code-only) [default: mixed]
  --force    Force re-index from scratch
```

### `analyze`

Analyze a GitHub issue against the indexed repository snapshot.

```bash
oss-issue-analyzer analyze <issue_ref> [OPTIONS]

Arguments:
  issue_ref        Issue number, URL, or path to local markdown file

Options:
  --repo           Path to indexed repository
  --db-path        Path to index database
  --embedder       Embedding model [default: minilm]
  --limit         Number of indexed units to retrieve [default: 10]
  --gh-repo       GitHub repo (owner/repo) - auto-detected if not provided
```

## Output Example

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

- `GITHUB_TOKEN` - GitHub personal access token for API rate limits
- `HF_TOKEN` - Hugging Face token for faster embedding downloads

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
```

## License

MIT
