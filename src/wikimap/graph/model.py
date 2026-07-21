"""networkx graph model plus the Step and MoveEvaluation contracts.

Contract 2: a Step describes what was added this tick (nodes, edges, a note).
Algorithms yield Steps; the server streams them over SSE; the frontend applies
them to vis-network. An algorithm must not know the renderer or transport exists.
"""
