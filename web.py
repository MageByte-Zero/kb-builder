#!/usr/bin/env python3
"""KB Builder Web UI — 启动入口"""
import argparse
import uvicorn

def main():
    parser = argparse.ArgumentParser(description="KB Builder Web UI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--config", default=None, help="config.yaml 路径")
    args = parser.parse_args()

    if args.config:
        import os
        os.environ["KB_CONFIG_PATH"] = args.config

    uvicorn.run("web.app:app", host=args.host, port=args.port, reload=False)

if __name__ == "__main__":
    main()
