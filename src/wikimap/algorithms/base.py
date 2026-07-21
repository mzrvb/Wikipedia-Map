"""Shared ABC(s) for all algorithms.

Every algorithm is a generator of Steps (contract 2) that reads its knobs from
config (contract 1). It never draws and never touches the transport.
"""
