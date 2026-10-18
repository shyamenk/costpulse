# Changelog

All notable changes to this project are documented here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- Project foundation: uv project, ruff, pytest, GitHub Actions CI, PR template.
- SAM template: Lambda (Python 3.14, arm64) with Function URL, explicit least-privilege IAM role, 14-day log retention, `AllowedChannelIds` parameter.
- Tests asserting the IAM role grants only the actions listed in the PRD (NFR3, NFR4, NFR8).
- PRD, milestones and backlog.
