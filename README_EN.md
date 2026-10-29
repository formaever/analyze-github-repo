# analyze-github-repo

[中文](README.md) | **English**

A read-only Agent Skill that analyzes public GitHub repositories or local source trees and explains their main features, architecture, execution flow, and implementation boundaries.

The goal is not to produce a project pitch, but to make conclusions **traceable, classified, and verifiable**:

- Separate author claims, source evidence, runtime evidence, and analysis inference.
- Attach file paths and line numbers to material implementation claims.
- Use a script to reject broken citations, then have the model review meaning.
- State uncovered areas and unknowns explicitly.

> This README is for repository documentation only. At runtime the skill loads only `SKILL.md`; this file is not read by the agent.

## What it does

- Classifies a project as an application, library, CLI, skill, or document collection.
- Traces a representative path from input through processing and external dependencies to output.
- Checks whether capabilities claimed in a README have actual implementation evidence.
- For skills, separates prompt requirements, helper scripts, and host-provided capabilities.
- Produces feature notes, limitations, and suitable use cases with source evidence.

## What it does not do

- Does not install dependencies, run scripts from the target repository, or modify its files.
- Does not call a valid citation location a semantic or factual verification.
- Does not treat examples, screenshots, or model scores as proof of real-world impact.
- Does not replace actual runtime testing, and does not report "works" when nothing was run.

## Layout

```text
analyze-github-repo/
├── SKILL.md                          # Main instructions and workflow
├── README.md                         # Chinese repository README
├── README_EN.md                      # This file
├── references/
│   └── domain-rules.md               # Claim classes, evidence rules, review criteria
├── scripts/
│   └── check_evidence.py             # Read-only citation location checker
├── examples/
│   ├── sample-repo/review_rules.py   # Synthetic source used for citations
│   ├── evidence-valid.json           # Valid citation example
│   └── evidence-invalid.json         # Missing file, out-of-range, path escape
└── tests/
    └── test_check_evidence.py        # Standard-library automated tests
```

## Install

Copy the whole directory into the target runtime's skills directory:

| Scope | Path |
|---|---|
| Qoder, project-level | `.qoder/skills/analyze-github-repo/` |
| Qoder, user-level | `~/.qoder/skills/analyze-github-repo/` |
| Claude Code and other compatible runtimes | The runtime's own `skills/` directory |

Restart the session or reload skills afterward, then confirm `analyze-github-repo` appears in the available skills list.

## Usage

Ask for an analysis directly:

```text
Analyze https://github.com/owner/repo and explain its main features and implementation.
Its README claims multi-agent support - is there an actual scheduler in the code?
Compare the error handling in these two repositories and cite the source.
```

Or invoke it explicitly:

```text
/analyze-github-repo analyze E:\WorkSpace\Qoder\btsou-mvp
```

Read-only by default. For remote repositories, follow the host's repository access and search tool rules.

## Evidence checker

Requires Python 3.9+. Standard library only. It does not use the network, execute target code, or write into the source tree.

```bash
python scripts/check_evidence.py <source-root> <evidence-json> --max-errors 20
```

Citation format:

```json
{
  "claims": [
    {
      "id": "C1",
      "claim": "Implementation claim to review",
      "file": "src/app.py",
      "start_line": 10,
      "end_line": 24
    }
  ]
}
```

What it checks:

- Field types and unique `id` values.
- Relative paths, drive letters, UNC paths, `..`, special characters, and symlink escapes.
- File existence and regular-file status.
- Valid line numbers within the file length.
- UTF-8 decoding, with optional BOM.

Exit codes:

| Code | Meaning |
|---|---|
| 0 | All citation locations are valid |
| 1 | Invalid citation location (missing file, out of range, path escape, etc.) |
| 2 | Argument, JSON, encoding, or read error |

`ok: true` means the locations are valid only. **It does not mean the claim is true or that the cited code supports it.**

Local demo, run from the skill directory:

```bash
python scripts/check_evidence.py examples/sample-repo examples/evidence-valid.json
python scripts/check_evidence.py examples/sample-repo examples/evidence-invalid.json
```

## Tests

```bash
python -m unittest discover -s tests -v
```

Current result: **31 tests, 30 passed, 1 skipped**.

The skipped case is the outside-symlink test because this Windows environment lacks the privilege to create symlinks. The outside-junction case passed for real, and a separate mocked-resolution test covers the same rejection branch.

## Design notes

- **Rules and scripts stay separate**: judgment criteria live in `references/`, mechanical checks live in `scripts/`.
- **Scripts do deterministic work only**: validate paths and line numbers; do not guess meaning or disguise keyword counts as understanding.
- **Evidence classes**: implementation evidence, runtime evidence, claim only, external dependency, unknown.
- **No pretending on failure**: when access or execution is unavailable, state the gap instead of filling it with speculation.

## Known limitations

- Validates citation locations, not whether the cited content supports the claim.
- Cannot read source that has encoding problems or lives on network paths.
- Static analysis cannot prove production behavior.
- Test coverage reflects the current implementation, not every platform and permission combination.
