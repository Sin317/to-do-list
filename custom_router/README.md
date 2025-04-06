# Mock Router Implementation

This project implements a mock router with packet forwarding capabilities and distance vector routing protocol with split horizon.

## Features

- Packet forwarding and queuing
- Distance Vector Routing Protocol
- Split Horizon implementation
- Neighbor management
- Routing table updates

## Project Structure

- `router.py`: Main router implementation
- `test_router.py`: Test cases for router functionality
- `requirements.txt`: Project dependencies

## Installation

1. Clone the repository
2. Install dependencies:
```bash
pip install -r requirements.txt
```

## Running Tests

To run the test suite:
```bash
pytest test_router.py
```

## Usage

```python
from router import Router, Packet

# Create a router
router = Router("R1")

# Add neighbors
router.add_neighbor("R2", 1)
router.add_neighbor("R3", 2)

# Create and send a packet
packet = Packet(source="R2", destination="R3", payload="Hello")
router.receive_packet(packet)

# Get routing table
routing_table = router.get_routing_table()
```

## Implementation Details

The router implements:
- Distance Vector Routing Protocol with Split Horizon
- Packet forwarding based on routing tables
- Neighbor management
- Network graph representation using NetworkX