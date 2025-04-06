from typing import Dict, List, Optional
import networkx as nx
import json
from dataclasses import dataclass
from datetime import datetime

@dataclass
class Packet:
    source: str
    destination: str
    payload: str
    timestamp: datetime = datetime.now()

class Router:
    def __init__(self, router_id: str):
        self.router_id = router_id
        self.routing_table: Dict[str, Dict[str, int]] = {}  # {destination: {next_hop: cost}}
        self.neighbors: Dict[str, int] = {}  # {neighbor_id: cost}
        self.packet_queue: List[Packet] = []
        self.network_graph = nx.Graph()
        
    def add_neighbor(self, neighbor_id: str, cost: int):
        """Add a neighbor router with associated cost."""
        self.neighbors[neighbor_id] = cost
        self.network_graph.add_edge(self.router_id, neighbor_id, weight=cost)
        self.update_routing_table()
        
    def remove_neighbor(self, neighbor_id: str):
        """Remove a neighbor router."""
        if neighbor_id in self.neighbors:
            del self.neighbors[neighbor_id]
            self.network_graph.remove_edge(self.router_id, neighbor_id)
            self.update_routing_table()
            
    def receive_packet(self, packet: Packet):
        """Receive a packet and either forward it or process it."""
        if packet.destination == self.router_id:
            self.packet_queue.append(packet)
            return True
        else:
            return self.forward_packet(packet)
            
    def forward_packet(self, packet: Packet) -> bool:
        """Forward a packet to the next hop based on routing table."""
        if packet.destination in self.routing_table:
            next_hop = min(self.routing_table[packet.destination].items(), 
                         key=lambda x: x[1])[0]
            # In a real implementation, this would send the packet to next_hop
            return True
        return False
        
    def update_routing_table(self):
        """Update routing table using distance vector algorithm with split horizon."""
        # Initialize routing table with direct neighbors
        self.routing_table = {self.router_id: {self.router_id: 0}}
        for neighbor, cost in self.neighbors.items():
            self.routing_table[neighbor] = {neighbor: cost}
            
        # Implement distance vector algorithm with split horizon
        for neighbor in self.neighbors:
            # In a real implementation, this would receive routing updates from neighbors
            # and apply split horizon rule
            pass
            
    def get_routing_table(self) -> Dict[str, Dict[str, int]]:
        """Return the current routing table."""
        return self.routing_table
        
    def get_packet_queue(self) -> List[Packet]:
        """Return the current packet queue."""
        return self.packet_queue 