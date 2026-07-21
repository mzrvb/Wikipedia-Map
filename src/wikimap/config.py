"""Every tunable knob, in one place, as data.

Contract 1: modes and algorithms read their settings from here and never hardcode.
Depth, node caps, branch caps (K=20), beam width, heuristic weights all live here.
Explore mode exists to watch these values reshape the graph.
"""
