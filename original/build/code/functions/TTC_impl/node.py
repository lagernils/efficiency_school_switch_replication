# Adapted from Luke Carani's matching-algorithms
# (https://github.com/lwcarani/matching-algorithms), with thanks, and modified
# substantially for the capacity-constrained school-switch setting. That
# repository carries no licence, so these files are not covered by the MIT
# licence at the repository root. Any remaining errors are our own.

from typing import Set, Tuple


class Node(object):
    def __init__(self, name: str):
        self.name: str = name
        self.incoming_edges: Set[Tuple[str, str]] = set()
        self.outgoing_edges: Set[Tuple[str, str]] = set()

    def __repr__(self):
        return f"Node({self.name})"

    def get_next_node(self) -> str:
        return list(self.outgoing_edges)[0][1]

    def degree_outgoing(self) -> int:
        return len(self.outgoing_edges)

    def degree_incoming(self) -> int:
        return len(self.incoming_edges)
