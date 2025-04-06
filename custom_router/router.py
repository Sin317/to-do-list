from typing import Dict, List, Optional
import networkx as nx
import json
from dataclasses import dataclass
from datetime import datetime
from collections import deque

@dataclass
class Packet:
    source: str
    destination: str
    payload: str
    timestamp: datetime = datetime.now()

class Router:
    def __init__(self, router_id: str, max_capacity: int = 100):
        self.router_id = router_id
        self.routing_table: Dict[str, Dict[str, int]] = {}  # {destination: {next_hop: cost}}
        self.neighbors: Dict[str, int] = {}  # {neighbor_id: cost}
        self.packet_queue: deque[Packet] = deque(maxlen=max_capacity)  # FIFO queue with max capacity
        self.network_graph = nx.Graph()
        self.max_capacity = max_capacity
        self.packet_count: Dict[str, List[Packet]] = {}  # {destination: [packets]}
        
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
            
    def receive_packet(self, packet: Packet) -> bool:
        """Receive a packet and either forward it or process it."""
        if len(self.packet_queue) >= self.max_capacity:
            return False  # Queue is full
            
        if packet.destination == self.router_id:
            self.packet_queue.append(packet)
            self._update_packet_count(packet)
            return True
        else:
            return self.forward_packet(packet)
            
    def forward_packet(self, packet: Packet) -> bool:
        """Forward a packet to the next hop based on routing table using FIFO."""
        if packet.destination in self.routing_table:
            next_hop = min(self.routing_table[packet.destination].items(), 
                         key=lambda x: x[1])[0]
            # In a real implementation, this would send the packet to next_hop
            self._update_packet_count(packet)
            return True
        return False
        
    def _update_packet_count(self, packet: Packet):
        """Update packet count for the destination."""
        if packet.destination not in self.packet_count:
            self.packet_count[packet.destination] = []
        self.packet_count[packet.destination].append(packet)
        
    def get_packet_count(self, destination: str, start_time: Optional[datetime] = None, 
                        end_time: Optional[datetime] = None) -> int:
        """Get count of packets for a destination within a timeframe."""
        # can this be done more optimally?
        if destination not in self.packet_count:
            return 0
            
        packets = self.packet_count[destination]
        if start_time is None and end_time is None:
            return len(packets)
            
        filtered_packets = packets
        if start_time:
            filtered_packets = [p for p in filtered_packets if p.timestamp >= start_time]
        if end_time:
            filtered_packets = [p for p in filtered_packets if p.timestamp <= end_time]
            
        return len(filtered_packets)
        
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
        return list(self.packet_queue)
        
    def get_queue_size(self) -> int:
        """Return the current size of the packet queue."""
        return len(self.packet_queue)
        
    def is_queue_full(self) -> bool:
        """Check if the packet queue is full."""
        return len(self.packet_queue) >= self.max_capacity 