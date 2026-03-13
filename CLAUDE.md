# CLAUDE.md

This file provides guidance for AI assistants (and developers) working in this repository.

## Project Overview

**Cluade** is a project repository for Claude-related tools and utilities. The project is in its early stages with foundational structure being established.

## Repository Structure

```
Cluade/
├── CLAUDE.md       # AI assistant guidance (this file)
└── README.md       # Project description
```

## Development Workflow

### Branching

- The default branch is `main`
- Feature branches should use the `claude/` prefix (e.g., `claude/feature-name-<id>`)
- Always push feature branches with `git push -u origin <branch-name>`

### Commits

- Write clear, descriptive commit messages
- Use imperative mood in commit subjects (e.g., "Add feature" not "Added feature")
- Keep commits focused — one logical change per commit

### Code Style

- Follow existing patterns and conventions in the codebase
- Keep files focused and avoid unnecessary bloat
- Prefer editing existing files over creating new ones when practical

## Key Conventions

- **No over-engineering**: Only add what is needed for the current task
- **Security first**: Never commit secrets, credentials, or `.env` files
- **Simplicity**: Favor straightforward solutions over clever abstractions

## Commands

No build system, test framework, or linting tools are configured yet. Update this section as tooling is added.

## For AI Assistants

- Read existing files before proposing changes
- Do not create files unless necessary
- Match the style and conventions already present in the codebase
- When in doubt, ask the user for clarification
