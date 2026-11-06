
"""
Database compaction module.

Owner: Person 2

Responsibilities:
- Remove outdated transaction records.
- Preserve the latest committed values.
- Shrink the database file.
- Survive crashes during compaction.
- Handle file-size limits safely.
"""
