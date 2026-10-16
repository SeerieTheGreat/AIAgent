"""Start and stop a local Anvil chain for development, tests and the judge mode."""
from __future__ import annotations

import os
import shutil
import subprocess
import time

from web3 import Web3


def anvil_path() -> str | None:
    return shutil.which("anvil") or (os.path.expanduser("~/.foundry/bin/anvil") if os.path.exists(os.path.expanduser("~/.foundry/bin/anvil")) else None)


class Anvil:
    def __init__(self, port: int = 8545, block_time: int | None = None):
        self.port = port
        self.block_time = block_time
        self.proc = None

    def __enter__(self):
        exe = anvil_path()
        if not exe:
            raise RuntimeError("anvil not found; install Foundry (https://getfoundry.sh)")
        args = [exe, "--port", str(self.port), "--silent"]
        if self.block_time:
            args += ["--block-time", str(self.block_time)]
        self.proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        url = f"http://127.0.0.1:{self.port}"
        for _ in range(100):
            try:
                if Web3(Web3.HTTPProvider(url)).is_connected():
                    return self
            except Exception:
                pass
            time.sleep(0.1)
        self.__exit__(None, None, None)
        raise RuntimeError("anvil did not start")

    def __exit__(self, *exc):
        if self.proc:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
            self.proc = None
