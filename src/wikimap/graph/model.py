"""The networkx graph wrapper. Consumes the Step contract from contracts.py.

Why wrap networkx instead of passing a raw DiGraph around: the same single-front-door
rule used for wikipediaapi (WikiClient) and sentence_transformers (Embedder). If every
caller poked at nx directly, swapping the graph backend or changing how a Step maps onto
nodes/edges would mean edits scattered everywhere. Here, one class owns that translation.

A DiGraph (directed), not a Graph, because Wikipedia links point one way — see Edge in
contracts.py.
"""

from __future__ import annotations

import networkx as nx

from wikimap.graph.contracts import Step


class WikiGraph:
    """Accumulates the live graph as algorithms emit Steps.

    The only mutating entry point is apply(step); everything else is read-only inspection
    for tests, pathfinding, and (later) serialization to the frontend.
    """

    def __init__(self) -> None:
        self._graph = nx.DiGraph()

    def apply(self, step: Step) -> None:
        """Fold one tick's nodes and edges into the graph.

        add_node/add_edge are idempotent in networkx: re-adding an existing node updates
        its attributes rather than duplicating it, and adding an edge whose endpoints
        don't exist yet auto-creates them. We add nodes first anyway so their score/depth
        attributes are set explicitly rather than left blank by an edge that raced ahead.
        """
        for node in step.nodes:
            self._graph.add_node(node.id, score=node.score, depth=node.depth)
        for edge in step.edges:
            self._graph.add_edge(edge.source, edge.target)

    def __contains__(self, title: str) -> bool:
        return title in self._graph

    def __len__(self) -> int:
        return self._graph.number_of_nodes()

    def has_edge(self, source: str, target: str) -> bool:
        return self._graph.has_edge(source, target)

    def neighbors(self, title: str) -> list[str]:
        """Successors of a node — the pages it links TO (out-edges only, since directed)."""
        return list(self._graph.successors(title))

    def node_attrs(self, title: str) -> dict:
        """The stored attributes (score, depth) for one node."""
        return dict(self._graph.nodes[title])
