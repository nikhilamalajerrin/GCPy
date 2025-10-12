from __future__ import annotations

import os
import subprocess
import tempfile

def _run_tf(tfdir: str, *args: str) -> bytes:
    terraform_binary = os.getenv("TERRAFORM_BINARY") or "terraform"
    cmd = [terraform_binary, *args]
    proc = subprocess.run(
        cmd, cwd=tfdir, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"Terraform command failed: {' '.join(cmd)}\n{proc.stderr.decode('utf-8', 'ignore')}"
        )
    return proc.stdout

def load_plan_json(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()

def generate_plan_json(tfdir: str, plan_path: str | None) -> bytes:
    if not tfdir:
        raise ValueError("--tfdir is required to generate plan JSON")

    if not plan_path:
        _run_tf(tfdir, "init")
        with tempfile.NamedTemporaryFile(prefix="tfplan-", delete=False) as tmp:
            tmp_plan = tmp.name
        try:
            _run_tf(tfdir, "plan", "-input=false", "-lock=false", f"-out={tmp_plan}")
            out = _run_tf(tfdir, "show", "-json", tmp_plan)
        finally:
            try:
                os.remove(tmp_plan)
            except OSError:
                pass
        return out

    return _run_tf(tfdir, "show", "-json", plan_path)
