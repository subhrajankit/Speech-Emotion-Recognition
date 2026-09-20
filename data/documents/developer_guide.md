# SenseAI Developer API Integration Guide

## WebSocket Streaming Concurrency Limits
Each organization API key is permitted up to 5 concurrent WebSocket connections to the /ws/voice endpoint. Additional attempted connections will be rejected with HTTP 429 Too Many Requests.

## Request Signature Authentication
All REST API mutations must supply an HMAC-SHA256 signature in the X-Sense-Signature header calculated using the client 32-byte secret key and the UTC unix timestamp.
