from __future__ import annotations

import os
import shlex
import subprocess
import tempfile
import logging
from dataclasses import dataclass
from typing import Optional, Sequence, Tuple


@dataclass
class CmdOptions:
    terraform_dir: str


def _no_color_enabled() -> bool:
    try:
        from plancosts import config  # type: ignore
        if hasattr(config, "Config") and hasattr(config.Config, "NoColor"):
            return bool(getattr(config.Config, "NoColor"))
        if hasattr(config, "no_color"):
            return bool(getattr(config, "no_color"))
    except Exception:
        pass
    return os.getenv("NO_COLOR") is not None


def _format_cmd(binary: str, args: Sequence[str]) -> str:
    return " ".join([shlex.quote(binary), *(shlex.quote(a) for a in args)])


def terraform_cmd(
    options: CmdOptions,
    *args: str,
) -> Tuple[bytes, Optional[Exception]]:
    terraform_binary = os.getenv("TERRAFORM_BINARY", "terraform")
    cmdline = [terraform_binary, *args]

    log = logging.getLogger(__name__)
    running_msg = f"Running command: {_format_cmd(terraform_binary, args)}"
    if _no_color_enabled():
        log.info(running_msg)
    else:
        log.info(f"\x1b[90m{running_msg}\x1b[0m")

    try:
        proc = subprocess.Popen(
            cmdline,
            cwd=options.terraform_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        stdout, stderr = proc.communicate()
    except Exception as e:
        return b"", e

    if stderr:
        for line in stderr.splitlines():
            try:
                log.error(line.decode("utf-8", errors="replace"))
            except Exception:
                log.error(str(line))

    if proc.returncode != 0:
        err = subprocess.CalledProcessError(
            proc.returncode, cmdline, output=stdout, stderr=stderr
        )
        return stdout or b"", err

    return stdout or b"", None


# ---------------- Plan helpers  ----------------

def load_plan_json(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def generate_plan_json(tfdir: str, plan_path: str | None = None) -> bytes:
    """
      - if plan_path is empty: terraform init; terraform plan -out=<tmp>; then show -json
      - else: terraform show -json <plan_path>
    """
    opts = CmdOptions(terraform_dir=tfdir)

    if not plan_path:
        # terraform init
        _, err = terraform_cmd(opts, "init")
        if err:
            raise err  # surface the CalledProcessError

        # create temp plan file
        with tempfile.NamedTemporaryFile(prefix="tfplan", delete=False) as tfp:
            plan_file = tfp.name

        try:
            # terraform plan -input=false -lock=false -out=<plan_file>
            _, err = terraform_cmd(
                opts, "plan", "-input=false", "-lock=false", f"-out={plan_file}"
            )
            if err:
                raise err

            plan_path = plan_file
            # fall through to show -json
            out, err = terraform_cmd(opts, "show", "-json", plan_path)
            if err:
                raise err
            return out or b""
        finally:
            try:
                os.remove(plan_file)
            except Exception:
                pass
    else:
        out, err = terraform_cmd(opts, "show", "-json", plan_path)
        if err:
            raise err
        return out or b""
