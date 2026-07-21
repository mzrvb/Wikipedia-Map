"""Two-layer cache: in-memory dict -> disk (data/) -> network.

Checked in that order; a network fetch writes to BOTH layers. Must be disk-backed
or every launch re-crawls from cold. No TTL for now — staleness is accepted.
"""
