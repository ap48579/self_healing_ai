"""Memory Graph & Groove Mechanics — per cortex_reasoning.md.

Strength lives on edges, not nodes. Edge weight = "groove depth": strengthened
by Hebbian co-activation + success, decayed by disuse (topic-scoped).
"""

from __future__ import annotations

import json
import math
import os
import time
from typing import Optional

import networkx as nx

DEFAULT_LAMBDA = 0.05  # decay rate per day, used when no topic-specific rate is set
SECONDS_PER_DAY = 86400.0


class MemoryGraph:
    """NetworkX-backed groove graph. Edge types:
    instance_of, co_retrieved_with, supersedes, contradicts.
    """

    def __init__(self, persist_path: Optional[str] = None):
        self.graph = nx.MultiDiGraph()
        self.persist_path = persist_path
        if persist_path and os.path.exists(persist_path):
            self.load()

    # ---- node / edge mutation ----

    def add_node(self, node_id: str, node_type: str, **attrs) -> None:
        if node_id in self.graph:
            self.graph.nodes[node_id].update(attrs)
        else:
            self.graph.add_node(node_id, node_type=node_type, **attrs)

    def add_edge(
        self,
        source: str,
        target: str,
        edge_type: str,
        weight: float = 0.5,
        topic: str = "default",
    ) -> None:
        self.graph.add_edge(
            source,
            target,
            key=edge_type,
            edge_type=edge_type,
            weight=weight,
            topic=topic,
            last_reinforced=time.time(),
        )

    def reinforce(
        self,
        source: str,
        target: str,
        edge_type: str,
        success: bool,
        learning_rate: float = 0.3,
    ) -> float:
        """Hebbian update rule from cortex_reasoning.md:
        retrieve + use + success -> strengthen.
        retrieve + ignored, or used + still failed -> flat or weaken.
        Returns the new weight.
        """
        if not self.graph.has_edge(source, target, key=edge_type):
            self.add_edge(source, target, edge_type, weight=0.5)

        data = self.graph[source][target][edge_type]
        current = data["weight"]
        if success:
            new_weight = current + learning_rate * (1.0 - current)
        else:
            new_weight = current - (learning_rate * 0.5) * current
        new_weight = max(0.01, min(1.0, new_weight))

        data["weight"] = new_weight
        data["last_reinforced"] = time.time()
        return new_weight

    # ---- decay ----

    def effective_weight(self, source: str, target: str, edge_type: str, now: Optional[float] = None) -> float:
        """Live decayed weight without mutating stored state — used at query time
        so freshness reflects elapsed time even between periodic decay passes."""
        if not self.graph.has_edge(source, target, key=edge_type):
            return 0.0
        data = self.graph[source][target][edge_type]
        now = now or time.time()
        days_elapsed = (now - data["last_reinforced"]) / SECONDS_PER_DAY
        lam = data.get("lambda_topic", DEFAULT_LAMBDA)
        return data["weight"] * math.exp(-lam * days_elapsed)

    def decay_all(self, lambda_by_topic: Optional[dict[str, float]] = None, now: Optional[float] = None) -> int:
        """Mutating decay pass — called periodically (piggybacks on Replay's
        decay+prune step). Returns count of edges below the prune threshold."""
        lambda_by_topic = lambda_by_topic or {}
        now = now or time.time()
        prune_candidates = 0
        for u, v, key, data in self.graph.edges(keys=True, data=True):
            lam = lambda_by_topic.get(data.get("topic", "default"), DEFAULT_LAMBDA)
            days_elapsed = (now - data["last_reinforced"]) / SECONDS_PER_DAY
            data["weight"] = data["weight"] * math.exp(-lam * days_elapsed)
            data["last_reinforced"] = now
            data["lambda_topic"] = lam
            if data["weight"] < 0.05:
                prune_candidates += 1
        return prune_candidates

    def prune(self, threshold: float = 0.05) -> list[tuple[str, str, str]]:
        """Archive (caller decides what 'archive' means) edges below threshold.
        Returns the removed (source, target, edge_type) triples."""
        to_remove = [
            (u, v, k)
            for u, v, k, d in self.graph.edges(keys=True, data=True)
            if d["weight"] < threshold
        ]
        for u, v, k in to_remove:
            self.graph.remove_edge(u, v, key=k)
        return to_remove

    # ---- retrieval: spreading activation ----

    def spreading_activation(
        self,
        seed_nodes: list[str],
        hops: int = 2,
        decay_per_hop: float = 0.5,
    ) -> dict[str, float]:
        """Walk outward from seed nodes along weighted edges. Activation
        propagates multiplicatively (edge weight * decay_per_hop per hop),
        so high-groove paths carry activation further than shallow ones."""
        activation: dict[str, float] = {n: 1.0 for n in seed_nodes if n in self.graph}
        frontier = dict(activation)

        for _ in range(hops):
            next_frontier: dict[str, float] = {}
            for node, node_activation in frontier.items():
                if node not in self.graph:
                    continue
                for _, target, edge_type in self.graph.out_edges(node, keys=True):
                    w = self.effective_weight(node, target, edge_type)
                    propagated = node_activation * w * decay_per_hop
                    if propagated < 0.01:
                        continue
                    incoming = activation.get(target, 0.0)
                    activation[target] = max(incoming, propagated)
                    next_frontier[target] = max(next_frontier.get(target, 0.0), propagated)
            frontier = next_frontier
            if not frontier:
                break

        for seed in seed_nodes:
            activation.pop(seed, None)
        return dict(sorted(activation.items(), key=lambda kv: kv[1], reverse=True))

    # ---- persistence ----

    def save(self, path: Optional[str] = None) -> None:
        path = path or self.persist_path
        if not path:
            raise ValueError("No persist_path configured")
        data = nx.node_link_data(self.graph, edges="edges")
        with open(path, "w") as f:
            json.dump(data, f)

    def load(self, path: Optional[str] = None) -> None:
        path = path or self.persist_path
        with open(path) as f:
            data = json.load(f)
        self.graph = nx.node_link_graph(data, edges="edges", multigraph=True, directed=True)

    def stats(self) -> dict:
        weights = [d["weight"] for _, _, d in self.graph.edges(data=True)]
        return {
            "nodes": self.graph.number_of_nodes(),
            "edges": self.graph.number_of_edges(),
            "mean_weight": sum(weights) / len(weights) if weights else 0.0,
            "max_weight": max(weights) if weights else 0.0,
            "min_weight": min(weights) if weights else 0.0,
        }
