# mock_pricing_api.py
import json
import os
import re
from http.server import BaseHTTPRequestHandler, HTTPServer

# -------------------
# Config via env vars
# -------------------
MODE = os.getenv("MOCK_MODE", "normal").lower()
#   normal     -> return one product per query (default)
#   multiple   -> return 2 products (to trigger "Multiple prices found..." warning)
#   none       -> return []
#   error      -> return HTTP 500

DEFAULT_PRICE = float(os.getenv("MOCK_BASE_PRICE", "0.0416"))

OVERRIDE = {
    # EC2 Compute Instance hours
    "EC2_INSTANCE_HR": float(os.getenv("MOCK_PRICE_EC2", "0.0416")),
    # EBS gp2/standard/sc1/st1 GB-month
    "EBS_GB": float(os.getenv("MOCK_PRICE_EBS_GB", "0.10")),
    # EBS io1 IOPS-month
    "EBS_IOPS": float(os.getenv("MOCK_PRICE_EBS_IOPS", "0.0002")),
    # EBS Snapshot GB-month
    "SNAPSHOT_GB": float(os.getenv("MOCK_PRICE_SNAPSHOT_GB", "0.05")),
    # ELB classic hours
    "ELB_CLASSIC_HR": float(os.getenv("MOCK_PRICE_ELB_CLASSIC", "0.025")),
    # ALB/NLB hours
    "ELB_ALB_HR": float(os.getenv("MOCK_PRICE_ELB_ALB", "0.0225")),
    "ELB_NLB_HR": float(os.getenv("MOCK_PRICE_ELB_NLB", "0.0225")),
    # NAT Gateway hours
    "NATGW_HR": float(os.getenv("MOCK_PRICE_NATGW_HR", "0.045")),
    # ---------- RDS ----------
    "RDS_INSTANCE_HR": float(os.getenv("MOCK_PRICE_RDS_INSTANCE_HR", "0.0416")),
    "RDS_STORAGE_GB": float(os.getenv("MOCK_PRICE_RDS_STORAGE_GB", "0.10")),
    "RDS_IOPS": float(os.getenv("MOCK_PRICE_RDS_IOPS", "0.00004")),
}


def _usd(price: float) -> dict:
    s = f"{price:.6f}"
    s = s.rstrip("0").rstrip(".") if "." in s else s
    return {"USD": s}


def _product(price: float) -> dict:
    return {"onDemandPricing": [{"priceDimensions": [{"pricePerUnit": _usd(price)}]}]}


# ---------- Attribute helpers (REGEX-aware) ----------


def _attrs_index(attrs):
    """Build an index: key -> list of dicts {op, value, raw}."""
    idx = {}
    for a in attrs or []:
        k = a.get("key", "")
        v = a.get("value", "")
        op = a.get("operation", "==").upper()
        idx.setdefault(k, []).append({"op": op, "value": v, "raw": a})
    return idx


def _match_value(op, expected, candidate):
    if op == "REGEX":
        pat = expected
        if isinstance(pat, str) and len(pat) >= 2 and pat[0] == "/" and pat[-1] == "/":
            pat = pat[1:-1]
        try:
            return re.search(pat, str(candidate)) is not None
        except re.error:
            return False
    return str(candidate) == str(expected)


def _get_last(idx, key):
    arr = idx.get(key, [])
    return arr[-1]["value"] if arr else ""


def _has(idx, key, expected=None, op=None):
    """True if any attribute with this key matches expected under op (or any if expected is None)."""
    for item in idx.get(key, []):
        if op and item["op"] != op.upper():
            continue
        if expected is None:
            return True
        if _match_value(item["op"], expected, item["value"]):
            return True
    return False


def _response_for_filters(attrs: list[dict]) -> list[dict]:
    """
    'Pricing engine':
    - respects operation REGEX for attributes
    - returns one/many/none products depending on MODE
    """
    idx = _attrs_index(attrs)

    service = _get_last(idx, "servicecode")
    family = _get_last(idx, "productFamily")

    price = DEFAULT_PRICE

    # -------- Decision table ----------
    # EC2 compute instance hours
    if service == "AmazonEC2" and family == "Compute Instance":
        price = OVERRIDE["EC2_INSTANCE_HR"]

    # EBS storage GB-month (gp2/standard/etc.)
    elif service == "AmazonEC2" and family == "Storage":
        price = OVERRIDE["EBS_GB"]

    # EBS IOPS-month
    elif (
        service == "AmazonEC2"
        and family == "System Operation"
        and (
            _has(idx, "usagetype", "/EBS:VolumeP-IOPS.piops/", op="REGEX")
            or _has(idx, "usagetype", "EBS:VolumeP-IOPS.piops")
        )
    ):
        price = OVERRIDE["EBS_IOPS"]

    # EBS Snapshot GB-month — ONLY match end-anchored SnapshotUsage (avoid ...UnderBilling)
    elif (
        service == "AmazonEC2"
        and family == "Storage Snapshot"
        and (
            _has(idx, "usagetype", "/EBS:SnapshotUsage$/", op="REGEX")  # anchored
            or _has(idx, "usagetype", "EBS:SnapshotUsage")  # exact
        )
    ):
        price = OVERRIDE["SNAPSHOT_GB"]

    # ELB/ALB/NLB hours
    elif service == "AWSELB" and ("Load Balancer" in family):
        if family == "Load Balancer":
            price = OVERRIDE["ELB_CLASSIC_HR"]
        elif family == "Load Balancer-Application":
            price = OVERRIDE["ELB_ALB_HR"]
        elif family == "Load Balancer-Network":
            price = OVERRIDE["ELB_NLB_HR"]

    # NAT Gateway hours
    elif (
        service == "AmazonEC2"
        and family == "NAT Gateway"
        and (
            _has(idx, "usagetype", "/NatGateway-Hours/", op="REGEX")
            or _has(idx, "usagetype", "NatGateway-Hours")
        )
    ):
        price = OVERRIDE["NATGW_HR"]

    # ---------- RDS pricing ----------
    elif service == "AmazonRDS" and family == "Database Instance":
        price = OVERRIDE["RDS_INSTANCE_HR"]
    elif service == "AmazonRDS" and family == "Database Storage":
        price = OVERRIDE["RDS_STORAGE_GB"]
    elif service == "AmazonRDS" and family == "Provisioned IOPS":
        price = OVERRIDE["RDS_IOPS"]

    # ------- Compose the products array based on MODE -------
    if MODE == "none":
        return []
    elif MODE == "multiple":
        return [_product(price), _product(price * 10.0)]
    else:
        return [_product(price)]


class H(BaseHTTPRequestHandler):
    def do_POST(self):
        # Optional: simulate server error
        if MODE == "error":
            self.send_error(500, "Simulated server error")
            return

        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8")

        try:
            queries = json.loads(body)
            if not isinstance(queries, list):
                queries = [queries]
        except Exception:
            queries = []

        resp = []
        for q in queries:
            attrs = (((q or {}).get("variables") or {}).get("filter") or {}).get(
                "attributes", []
            )
            products = _response_for_filters(attrs)
            resp.append({"data": {"products": products}})

        out = json.dumps(resp).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)


# -------------------
# Self-tests (no pytest)
# -------------------


def _normalize_tenancy(v):
    return "Dedicated" if f"{v}" == "dedicated" else "Shared"


def _run_self_tests():
    from plancosts.base.filters import ValueMapping, map_filters

    # 1) Tenancy normalization
    vm_inst = ValueMapping(
        from_key="tenancy", to_key="tenancy", map_func=_normalize_tenancy
    )
    vm_lc = ValueMapping(
        from_key="placement_tenancy", to_key="tenancy", map_func=_normalize_tenancy
    )
    assert any(
        f.key == "tenancy" and f.value == "Dedicated"
        for f in map_filters([vm_inst], {"tenancy": "dedicated"})
    )
    assert any(
        f.key == "tenancy" and f.value == "Shared"
        for f in map_filters([vm_inst], {"tenancy": "default"})
    )
    assert any(
        f.key == "tenancy" and f.value == "Dedicated"
        for f in map_filters([vm_lc], {"placement_tenancy": "dedicated"})
    )
    assert any(
        f.key == "tenancy" and f.value == "Shared"
        for f in map_filters([vm_lc], {"placement_tenancy": "default"})
    )

    # 2) Snapshot pricing: anchored match and exact match pass
    attrs_snapshot_regex = [
        {"key": "servicecode", "value": "AmazonEC2", "operation": "=="},
        {"key": "productFamily", "value": "Storage Snapshot", "operation": "=="},
        {"key": "usagetype", "value": "/EBS:SnapshotUsage$/", "operation": "REGEX"},
    ]
    assert _response_for_filters(
        attrs_snapshot_regex
    ), "Anchored SnapshotUsage regex should match"

    attrs_snapshot_exact = [
        {"key": "servicecode", "value": "AmazonEC2", "operation": "=="},
        {"key": "productFamily", "value": "Storage Snapshot", "operation": "=="},
        {"key": "usagetype", "value": "EBS:SnapshotUsage", "operation": "=="},
    ]
    assert _response_for_filters(
        attrs_snapshot_exact
    ), "Exact SnapshotUsage should match"

    # 2b) UnderBilling must NOT match
    attrs_snapshot_underbilling = [
        {"key": "servicecode", "value": "AmazonEC2", "operation": "=="},
        {"key": "productFamily", "value": "Storage Snapshot", "operation": "=="},
        {
            "key": "usagetype",
            "value": "EBS:SnapshotUsageUnderBilling",
            "operation": "==",
        },
    ]
    assert (
        _response_for_filters(attrs_snapshot_underbilling) == []
    ), "UnderBilling must not match"

    # 3) Fixture smoke: exercise 8GB default path (no size in root_block_device)
    with open("test.json", "r", encoding="utf-8") as f:
        plan = json.load(f)

    inst = next(
        r
        for r in plan["planned_values"]["root_module"]["resources"]
        if r["address"] == "aws_instance.example"
    )
    lc = next(
        r
        for r in plan["planned_values"]["root_module"]["resources"]
        if r["address"] == "aws_launch_configuration.lc1"
    )

    def _no_size_block(b):
        return b in (None, [], {}) or (
            isinstance(b, list)
            and b
            and isinstance(b[0], dict)
            and not any(k in b[0] for k in ("size", "volume_size"))
        )

    assert _no_size_block(
        inst["values"].get("root_block_device")
    ), "Fixture should omit instance root_block_device size"
    assert _no_size_block(
        lc["values"].get("root_block_device")
    ), "Fixture should omit LC root_block_device size"

    print("SELF TESTS PASSED")


if __name__ == "__main__":
    if os.getenv("SELF_TEST", "0") == "1":
        _run_self_tests()
    else:
        print(
            "Mock pricing API on http://127.0.0.1:4000/  (set PLANCOSTS_API_URL=http://127.0.0.1:4000)"
        )
        print(f"MODE={MODE}  DEFAULT_PRICE={DEFAULT_PRICE}")
        for k, v in OVERRIDE.items():
            print(f"  {k}={v}")
        #HTTPServer(("127.0.0.1", 4000), H).serve_forever() for local CLI
        HTTPServer(("0.0.0.0", 4000), H).serve_forever()
