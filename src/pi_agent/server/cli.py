"""pi-squared 命令行入口。

用法：
    pi-squared serve [--host 127.0.0.1] [--port 8000] [--data ~/.pi-squared]
"""
import argparse
from pathlib import Path

import uvicorn

from pi_agent.server.app import create_app


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="pi-squared", description="Pi² agent server")
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="启动网关服务")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--data", default=str(Path.home() / ".pi-squared"), help="数据目录（会话/工作区）")

    args = parser.parse_args(argv)

    if args.command == "serve":
        data_dir = Path(args.data).expanduser().resolve()
        workspace_root = data_dir / "workspaces"
        data_dir.mkdir(parents=True, exist_ok=True)
        workspace_root.mkdir(parents=True, exist_ok=True)

        app = create_app(data_dir, workspace_root)
        print(f"[pi-squared] 数据目录   {data_dir}")
        print(f"[pi-squared] 工作区根   {workspace_root}")
        print(f"[pi-squared] 服务地址   http://{args.host}:{args.port}")
        uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
