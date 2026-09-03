# Neo4j initialization

This directory is mounted writable because the Neo4j container startup path may normalize ownership of imported initialization material. Durable graph data itself is stored in the Docker-managed Neo4j volume.

Typed ECDAT node/edge semantics remain in domain properties while the adapter uses the generic `ECDATNode` / `ECDAT_REL` envelope for interoperable persistence.
