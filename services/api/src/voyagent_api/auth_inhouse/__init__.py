"""In-house authentication subsystem for the Voyagent API.

Replaces the v0 Clerk integration with a self-hosted email + password
service backed by argon2id, HS256 access JWTs, and hashed refresh
tokens persisted in Postgres. See ``routes.py`` for the wire contract.
"""

from __future__ import annotations
