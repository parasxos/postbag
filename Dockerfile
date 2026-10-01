# Introspection-only container for directory health checks such as Glama's.
# postbag delivers letters through a host session's native door, so inside a
# container every join and send refuses for lack of a session. The server still
# starts and answers initialize and tools/list with the full tool catalog.
FROM python:3.12-slim
ARG POSTBAG_VERSION=2.1.0
RUN pip install --no-cache-dir "postbag[mcp]==${POSTBAG_VERSION}"
ENTRYPOINT ["postbag-mcp"]
