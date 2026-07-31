"""Connect mode: Wikipedia speedrun from page A to page B.

Top-K branching is ranked by similarity to the TARGET — this ranking IS the
greedy/A* heuristic (decision C). `bfs` is the deliberate exception: uncapped and
bidirectional, it exists to grade the other two, not to obey decision C itself —
see its module docstring.

`ALGORITHMS` is the registry the server picks from. It lives here rather than in
server/app.py because *which Connect algorithms exist* is domain knowledge, not
transport knowledge — the server should be able to offer a new one without learning
anything about it beyond the name. Every value is a ConnectAlgorithm subclass, so the
ABC's guarantee (each provides `run`) is what makes them interchangeable.
"""

from wikimap.algorithms.connect.astar import AStarConnect
from wikimap.algorithms.connect.bfs import BFSConnect
from wikimap.algorithms.connect.default import DefaultConnect
from wikimap.algorithms.connect.greedy import GreedyConnect

ALGORITHMS = {
    "greedy": GreedyConnect,
    "astar": AStarConnect,
    "bfs": BFSConnect,
    "default": DefaultConnect,
}

# Bidirectional weighted A* (default.py) — top-K capped like astar, searched from
# both ends like bfs, so it's usually the cheapest AND least visually explosive
# choice for someone who just wants a good route without picking an algorithm.
# See default.py's module docstring for why it is still not provably optimal.
DEFAULT_ALGORITHM = "default"
