"""The Step contract (contract 2) and its WikiGraph consumer.

Pure structure — no network, no model, no algorithms — so these are all fast.
"""

from wikimap.graph.contracts import Edge, Grade, MoveEvaluation, Node, Step
from wikimap.graph.model import WikiGraph


class TestStepApplication:
    def test_apply_adds_nodes_with_attrs(self):
        g = WikiGraph()
        g.apply(Step(nodes=[Node(id="Cat", score=0.42, depth=1)]))
        assert "Cat" in g
        assert g.node_attrs("Cat") == {"score": 0.42, "depth": 1}

    def test_apply_adds_directed_edge(self):
        g = WikiGraph()
        g.apply(
            Step(
                nodes=[Node(id="Cat"), Node(id="Astronomy")],
                edges=[Edge(source="Cat", target="Astronomy")],
            )
        )
        # The edge exists one way only — Wikipedia links are directional.
        assert g.has_edge("Cat", "Astronomy")
        assert not g.has_edge("Astronomy", "Cat")

    def test_neighbors_are_successors_only(self):
        g = WikiGraph()
        g.apply(
            Step(
                nodes=[Node(id="Cat"), Node(id="Lion"), Node(id="Pet")],
                edges=[Edge("Cat", "Lion"), Edge("Cat", "Pet")],
            )
        )
        assert sorted(g.neighbors("Cat")) == ["Lion", "Pet"]
        assert g.neighbors("Lion") == []  # Lion links to nothing yet

    def test_reapplying_a_node_updates_not_duplicates(self):
        g = WikiGraph()
        g.apply(Step(nodes=[Node(id="Cat", depth=1)]))
        g.apply(Step(nodes=[Node(id="Cat", depth=1, score=0.9)]))
        assert len(g) == 1
        assert g.node_attrs("Cat")["score"] == 0.9

    def test_empty_step_is_a_noop(self):
        g = WikiGraph()
        g.apply(Step())
        assert len(g) == 0


class TestContracts:
    def test_grade_serializes_as_its_word(self):
        # str-Enum: the member IS the string, ready for JSON/SSE with no conversion.
        assert Grade.BEST == "Best"
        assert Grade.BRILLIANT.value == "Brilliant"

    def test_move_evaluation_holds_the_five_fields(self):
        m = MoveEvaluation(
            from_="Cat", to="Astronomy", grade=Grade.GOOD, delta=0.12, note="closer"
        )
        assert m.from_ == "Cat"
        assert m.to == "Astronomy"
        assert m.grade is Grade.GOOD
        assert m.delta == 0.12
