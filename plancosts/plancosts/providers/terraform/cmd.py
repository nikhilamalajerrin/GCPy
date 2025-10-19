from __future__ import annotations

import os
import shlex
import subprocess
import tempfile
import threading
import logging
from dataclasses import dataclass
from typing import Optional, Sequence, Tuple


@dataclass
class CmdOptions:
    terraform_dir: str


def _no_color_enabled() -> bool:
    """
    Mirror Go: config.Config.NoColor if present; otherwise honor NO_COLOR env.
    """
    try:
        from plancosts import config  # type: ignore[attr-defined]
        if hasattr(config, "Config") and hasattr(config.Config, "NoColor"):
            return bool(getattr(config.Config, "NoColor"))
        if hasattr(config, "no_color"):
            return bool(getattr(config, "no_color"))
    except Exception:
        pass
    return os.getenv("NO_COLOR") is not None


def _format_cmd(binary: str, args: Sequence[str]) -> str:
    return " ".join([shlex.quote(binary), *(shlex.quote(a) for a in args)])


def _log_running_cmd(logger: logging.Logger, binary: str, args: Sequence[str]) -> None:
    msg = f"Running command: {_format_cmd(binary, args)}"
    if _no_color_enabled():
        logger.info(msg)
    else:
        # bright black (dim gray)
        logger.info("\x1b[90m%s\x1b[0m", msg)


def terraform_cmd(
    options: CmdOptions,
    *args: str,
) -> Tuple[bytes, Optional[Exception]]:
    """
    Run a terraform subcommand in the given directory, streaming stderr to the logger.
    Returns (stdout_bytes, error). On non-zero exit, error is a CalledProcessError.
    """
    terraform_binary = os.getenv("TERRAFORM_BINARY", "terraform")
    cmdline = [terraform_binary, *args]

    log = logging.getLogger(__name__)
    _log_running_cmd(log, terraform_binary, args)

    try:
        proc = subprocess.Popen(
            cmdline,
            cwd=options.terraform_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=1,  # line-buffer stderr reader
            text=True,  # decode to str for streaming
        )
    except Exception as e:
        return b"", e

    # Stream stderr lines to logger as they arrive.
    def _pump_stderr(p: subprocess.Popen) -> None:
        assert p.stderr is not None
        for line in p.stderr:
            # already str because text=True
            log.error(line.rstrip("\n"))

    t = threading.Thread(target=_pump_stderr, args=(proc,), daemon=True)
    t.start()

    # Collect stdout (as bytes, to match previous API)
    stdout_str = ""
    if proc.stdout is not None:
        try:
            stdout_str = proc.stdout.read()
        finally:
            try:
                proc.stdout.close()
            except Exception:
                pass

    # Wait for process & stderr pump to finish
    proc.wait()
    t.join(timeout=0.1)

    stdout_bytes = stdout_str.encode("utf-8", errors="replace")

    if proc.returncode != 0:
        err = subprocess.CalledProcessError(
            proc.returncode, cmdline, output=stdout_bytes
        )
        return stdout_bytes, err

    return stdout_bytes, None


# ---------------- Plan helpers ----------------

def load_plan_json(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def generate_plan_json(tfdir: str, plan_path: str | None = None) -> bytes:
    """
    - If plan_path is empty:
        terraform init
        terraform plan -input=false -lock=false -out=<tmpfile>
        terraform show -json <tmpfile>
      The temp plan file is removed after 'show'.
    - Else:
        terraform show -json <plan_path>
    """
    opts = CmdOptions(terraform_dir=tfdir)

    if not plan_path:
        # terraform init
        _, err = terraform_cmd(opts, "init")
        if err:
            raise err  # propagate CalledProcessError

        # temp plan file
        fd, plan_file = tempfile.mkstemp(prefix="tfplan", dir=None, text=False)
        os.close(fd)
        try:
            # terraform plan
            _, err = terraform_cmd(
                opts, "plan", "-input=false", "-lock=false", f"-out={plan_file}"
            )
            if err:
                raise err

            # terraform show -json
            out, err = terraform_cmd(opts, "show", "-json", plan_file)
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


# ---------------- Version helper (first line only) ----------------

def terraform_version() -> Tuple[str, Optional[Exception]]:
    """
    Run 'terraform -version' using TERRAFORM_BINARY (default 'terraform').
    Return (first_line_with_newline, error). On success, error is None.

    Mirrors Go change:
      out, err := exec.Command(terraformBinary, "-version").Output()
      firstLine := string(out)[0:strings.Index(string(out), "\n")]
      fmt.Println(firstLine)
    """
    terraform_binary = os.getenv("TERRAFORM_BINARY", "terraform")
    try:
        proc = subprocess.run(
            [terraform_binary, "-version"],
            check=False,
            capture_output=True,
            text=True,
        )
    except Exception as e:
        return "", e

    out = proc.stdout or ""
    first_line = ""
    if out:
        # Take text up to the first newline (or whole string if single line)
        first_line = out.splitlines()[0] if "\n" in out else out

    if proc.returncode == 0:
        # Include trailing newline to match fmt.Println(firstLine)
        return (first_line + ("\n" if not first_line.endswith("\n") else "")), None

    # Non-zero exit: return whatever we got plus an error
    return (first_line + ("\n" if first_line and not first_line.endswith("\n") else "")), subprocess.CalledProcessError(
        proc.returncode, [terraform_binary, "-version"], output=proc.stdout, stderr=proc.stderr
    )
