"""In-house authentication subsystem for the Voyagent API.

Self-hosted email + password service backed by argon2id password
hashing, HS256 access JWTs, and hashed refresh tokens persisted in
Postgres. See ``routes.py`` for the wire contract.
"""

from __future__ import annotations
