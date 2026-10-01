# Image for directory health checks such as Glama's: it starts the MCP server and
# answers initialize and tools/list with the full tool catalog. postbag delivers
# letters through a host session's native door, which a container does not have,
# so native delivery from this image is unsupported and unverified.
FROM python:3.12-slim
ARG POSTBAG_VERSION=2.2.0
RUN pip install --no-cache-dir "postbag[mcp]==${POSTBAG_VERSION}"
ENTRYPOINT ["postbag-mcp"]
