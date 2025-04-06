import pytest
from router import Router, Packet
from datetime import datetime

def test_router_initialization():
    router = Router("R1")
    assert router.router_id == "R1"
    assert len(router.neighbors) == 0
    assert len(router.packet_queue) == 0

def test_add_neighbor():
    router = Router("R1")
    router.add_neighbor("R2", 1)
    assert "R2" in router.neighbors
    assert router.neighbors["R2"] == 1
    assert "R2" in router.routing_table

def test_remove_neighbor():
    router = Router("R1")
    router.add_neighbor("R2", 1)
    router.remove_neighbor("R2")
    assert "R2" not in router.neighbors
    assert "R2" not in router.routing_table

def test_receive_packet():
    router = Router("R1")
    packet = Packet(source="R2", destination="R1", payload="test")
    assert router.receive_packet(packet) is True
    assert len(router.packet_queue) == 1
    assert router.packet_queue[0].payload == "test"

def test_forward_packet():
    router = Router("R1")
    router.add_neighbor("R2", 1)
    router.add_neighbor("R3", 2)
    packet = Packet(source="R2", destination="R3", payload="test")
    assert router.forward_packet(packet) is True

def test_routing_table_update():
    router = Router("R1")
    router.add_neighbor("R2", 1)
    router.add_neighbor("R3", 2)
    routing_table = router.get_routing_table()
    assert "R2" in routing_table
    assert "R3" in routing_table
    assert routing_table["R2"]["R2"] == 1
    assert routing_table["R3"]["R3"] == 2 