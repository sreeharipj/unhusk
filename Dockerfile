# Build stage
FROM rust:1.85-slim-bookworm AS builder
WORKDIR /usr/src/unhusk
COPY . .
RUN cargo build --release

# Final stage
FROM debian:bookworm-slim
# Install any necessary runtime dependencies if needed in the future
# RUN apt-get update && apt-get install -y <deps> && rm -rf /var/lib/apt/lists/*
COPY --from=builder /usr/src/unhusk/target/release/unhusk /usr/local/bin/unhusk

ENTRYPOINT ["unhusk"]
