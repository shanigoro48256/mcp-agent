#!/bin/bash

scripts=(
  "search_mcp_server.py"
  "rag_mcp_server.py"
  "db_mcp_server.py"
  "fs_mcp_server.py"
  )

for script in "${scripts[@]}"
do
  echo "Starting $script..."
  python "$script" &
done

wait
