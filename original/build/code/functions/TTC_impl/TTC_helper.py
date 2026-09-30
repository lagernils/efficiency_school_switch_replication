# Adapted from Luke Carani's matching-algorithms
# (https://github.com/lwcarani/matching-algorithms), with thanks, and modified
# substantially for the capacity-constrained school-switch setting. That
# repository carries no licence, so these files are not covered by the MIT
# licence at the repository root. Any remaining errors are our own.

# standard imports
from typing import List, Dict, Set

# custom imports
from .graph import Graph
from .node import Node


## UNUSED — superseded by find_all_cycles. Kept for reference only.
## NOTE: the guard below has a latent bug — `G.number_of_nodes_in_graph`
## is a bound method, not a call, so the comparison to 0 is always False.
## def find_cycle(G: Graph) -> List[str] | None:
##     if G.number_of_nodes_in_graph == 0:
##         return None
##     visited_nodes: Set[str] = set()
##     cycle: List[str] = list()
##     # start at an arbitrary node in the graph to begin random walk
##     # repeat until we find a cycle. NOTE: a cycle is guaranteed to exist.
##     n: Node = G.get_random_node()
##     while n.name not in visited_nodes:
##         visited_nodes.add(n.name)
##         cycle.append(n.name)
##         n: Node = G.nodes[n.get_next_node()]
##
##     start_of_cycle_index = cycle.index(n.name)
##     return cycle[start_of_cycle_index:]


def find_all_cycles(G: Graph) -> List[List[str]]:
    """Return a list of all directed cycles in the current outdegree-1 graph G.

    Each cycle is returned as a list of node names in traversal order. Cycles are
    pairwise disjoint in an outdegree-1 graph; this routine scans the graph once
    and discovers every cycle present in the snapshot.
    """
    cycles: List[List[str]] = []
    processed: Set[str] = set()

    # Iterate deterministically over nodes to get reproducible cycle ordering
    for start in list(G.nodes.keys()):
        if start in processed:
            continue
        # skip nodes that cannot be in a cycle
        if start not in G.nodes or G.nodes[start].degree_outgoing() == 0:
            processed.add(start)
            continue

        path: List[str] = []
        index_of: Dict[str, int] = {}
        u = start
        while True:
            if u not in G.nodes:
                # reached a node that was removed; mark path processed and stop
                for p in path:
                    processed.add(p)
                break
            if G.nodes[u].degree_outgoing() == 0:
                # dead end, mark path processed and stop
                for p in path:
                    processed.add(p)
                break
            if u in processed:
                # already handled via another traversal
                for p in path:
                    processed.add(p)
                break
            if u in index_of:
                # found a cycle
                cyc = path[index_of[u] :]
                cycles.append(cyc)
                for p in cyc:
                    processed.add(p)
                # also mark nodes that led into the cycle
                for p in path[: index_of[u]]:
                    processed.add(p)
                break

            index_of[u] = len(path)
            path.append(u)
            # follow the unique outgoing neighbor
            u = G.nodes[u].get_next_node()

    return cycles


def update_graph(
    G,
    matches,
    student_preferences,
    school_preferences,
    student_queue,
    school_queue,
    c,
    remaining_schools,
):
    # current nodes in graph
    current_nodes = set(G.nodes.keys())

    # handle students: if a student has no outgoing edge, point them to their next preferred school that still has capacity
    for i in list(current_nodes):
        if i in student_preferences and i in G.nodes.keys() and G.nodes.get(i).degree_outgoing() == 0:
            # advance student's pointer until we find a remaining school
            while True:
                student_queue[i] += 1
                school_index = student_queue[i]
                if school_index < len(student_preferences[i]):
                    next_school_preference: str = student_preferences[i][school_index]
                else:
                    # exhausted preferences: mark unmatched and remove student
                    matches[i] = i
                    G.delete_node(i)
                    break

                # only add edge if school still has remaining capacity and is present in graph
                if next_school_preference in remaining_schools and next_school_preference in G.nodes:
                    G.add_edge(i, next_school_preference)
                    break

    # handle schools: if a school has no outgoing edge, point it to its highest-priority remaining student
    for sc in list(current_nodes):
        if sc in school_preferences and sc in G.nodes.keys() and G.nodes.get(sc).degree_outgoing() == 0:
            # increment counter so that next time through loop, we consider the next student on the priority list
            while True:
                student_queue[sc] += 1
                student_index = student_queue[sc]
                if student_index < len(school_preferences[sc]):
                    next_student_preference: str = school_preferences[sc][student_index]
                else:
                    # no remaining preferred students; remove school
                    if sc in G.nodes:
                        G.delete_node(sc)
                    remaining_schools.discard(sc)
                    break

                # if this school's next highest preference is still present, add edge
                if next_student_preference in G.nodes:
                    G.add_edge(sc, next_student_preference)
                    break

    return G, matches, student_queue, school_queue, c, remaining_schools
