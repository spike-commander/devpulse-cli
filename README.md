# devpulse

A small CLI for the daily developer chores that nobody actually enjoys:
checking on your pull requests, cleaning up dead branches, and figuring out
what on earth is in your notes folder.

Built for an MLH Fellowship application. No web framework, no notebooks, no
fake data — everything on screen comes from a real API call or a real git
process.

## What it does

| Command | What it's for |
| --- | --- |
| `devpulse status` | Lists your open PRs from the GitHub API: title, repo, branch, age, and a live CI/CD signal. |
| `devpulse prune` | Syncs remotes, then lists local branches that are fully merged into a base branch and safe to delete. |
| `devpulse scan` | Walks a Markdown folder and prints a per-file inventory (lines, words, headings). |

## Requirements

- Python 3.11+
- `git` on PATH (needed by `prune` and for repo detection)
- a GitHub personal access token for `status`

## Install

```bash
poetry install
poetry run devpulse --help
```

No Poetry? `pip install .` works too, and `python main.py` can be used
without installing anything at all.

## Usage

### Status

```bash
export GITHUB_TOKEN=ghp_...
devpulse status
# or pass it inline:
devpulse status --token ghp_...
```

This runs `is:open is:pr author:@me` against the GitHub search API. Since the
search results don't include commit status, each PR gets a follow-up call for
its head commit's combined status — they run concurrently, so even with a
handful of PRs it stays snappy. The CI column shows:

- `SUCCESS` — checks passing
- `FAILURE` — something broke
- `PENDING` — still running
- `NO STATUS` — repo has no status checks

Bad tokens, rate limits, timeouts, and network failures are all caught and
printed as plain-language errors.

### Prune

```bash
devpulse prune                  # dry run: what's merged into main?
devpulse prune --base develop   # against another branch
devpulse prune --delete         # actually delete them
```

It first runs `git remote update --prune` so your local view matches upstream,
then lists local branches fully merged into the base. Safe by default:
`--delete` uses `git branch -d`, so branches with unpushed or unmerged
commits are left alone.

Outside a git repo it just tells you where you went wrong.

### Scan

```bash
devpulse scan                        # index **/*.md under the current dir
devpulse scan --path notes/
devpulse scan --path README.md       # single file
```

## Layout

```
devpulse/
├── pyproject.toml
├── README.md
├── main.py                       # python main.py
└── devpulse/
    ├── __init__.py
    ├── cli.py                    # commands: status, prune, scan
    ├── core/
    │   └── git_client.py         # subprocess wrapper around git
    ├── services/
    │   └── github_svc.py         # async GitHub REST client
    └── utils/
        └── visualizer.py         # tables, panels, spinners
```

## Notes on the design

- **Typed end to end.** Every public signature carries explicit annotations.
- **Async where it matters.** The GitHub client is a single `httpx.AsyncClient`
  used as a context manager; per-PR lookups go out with `asyncio.gather`, and
  the CLI coordinates them with `asyncio.run()`.
- **Layers stay separate.** `core` talks to this machine, `services` talks to
  the network, `visualizer` only draws, and `cli.py` merely wires them up.
- **No mock data.** If a command shows you something, something real produced it.

## License

MIT