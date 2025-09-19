# mock_pricing_api.py
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
import re

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
    # EBS Snapshot GB-month (with usagetype=EBS:SnapshotUsage)
    "SNAPSHOT_GB": float(os.getenv("MOCK_PRICE_SNAPSHOT_GB", "0.05")),
    # ELB classic hours
    "ELB_CLASSIC_HR": float(os.getenv("MOCK_PRICE_ELB_CLASSIC", "0.025")),
    # ALB hours
    "ELB_ALB_HR": float(os.getenv("MOCK_PRICE_ELB_ALB", "0.0225")),
    # NLB hours
    "ELB_NLB_HR": float(os.getenv("MOCK_PRICE_ELB_NLB", "0.0225")),
    # NAT Gateway hours
    "NATGW_HR": float(os.getenv("MOCK_PRICE_NATGW_HR", "0.045")),
}

def _usd(price: float) -> dict:
    return {"USD": f"{price:.6f}".rstrip("0").rstrip(".") if "." in f"{price:.6f}" else f"{price:.6f}"}

def _product(price: float) -> dict:
    return {
        "onDemandPricing": [{
            "priceDimensions": [{
                "pricePerUnit": _usd(price)
            }]
        }]
    }

def _response_for_filters(attrs: list[dict]) -> list[dict]:
    """
    Very small 'pricing engine':
    - looks at servicecode/productFamily/usagetype filters
    - returns one/many/none products depending on MODE
    """
    # Normalize attributes into a quick dict: key -> [(op, val), ...]
    bykey: dict[str, list[tuple[str, str]]] = {}
    for a in attrs or []:
        k = a.get("key", "")
        op = a.get("operation", "")
        v = a.get("value", "")
        bykey.setdefault(k, []).append((op, v))

    def has(key: str, needle: str | None = None) -> bool:
        if key not in bykey:
            return False
        if needle is None:
            return True
        for op, val in bykey[key]:
            if op == "REGEX":
                # treat value "/X.Y/" as a pattern without the slashes
                pat = val.strip("/")
                try:
                    if re.search(pat, needle) or re.search(pat, val):
                        return True
                except re.error:
                    pass
                # also allow substring fallback
                if pat in needle or needle in val:
                    return True
            if needle == val:
                return True
        return False

    service = next((v for _, v in bykey.get("servicecode", [])[-1:]), "")
    family  = next((v for _, v in bykey.get("productFamily", [])[-1:]), "")
    usg     = next((v for _, v in bykey.get("usagetype",   [])[-1:]), "")

    price = DEFAULT_PRICE

    # -------- Decision table ----------
    # EC2 compute instance hours
    if service == "AmazonEC2" and family == "Compute Instance":
        price = OVERRIDE["EC2_INSTANCE_HR"]

    # EBS storage GB-month (gp2/standard/etc.)
    elif service == "AmazonEC2" and family == "Storage":
        price = OVERRIDE["EBS_GB"]

    # EBS IOPS-month
    elif service == "AmazonEC2" and family == "System Operation" and ("EBS:VolumeP-IOPS.piops" in usg or "EBS:VolumeP-IOPS.piops" in str(bykey.get("usagetype", ""))):
        price = OVERRIDE["EBS_IOPS"]

    # EBS Snapshot GB-month (this commit added 'EBS:SnapshotUsage' filter)
    elif service == "AmazonEC2" and family == "Storage Snapshot" and ("EBS:SnapshotUsage" in usg or "EBS:SnapshotUsage" in str(bykey.get("usagetype", ""))):
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
    elif service == "AmazonEC2" and family == "NAT Gateway" and ("NatGateway-Hours" in usg or "NatGateway-Hours" in str(bykey.get("usagetype", ""))):
        price = OVERRIDE["NATGW_HR"]

    # ------- Compose the products array based on MODE -------
    if MODE == "none":
        return []  # no products
    elif MODE == "multiple":
        # two products, first is the one your code should use
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

        # Each query is {"query": "...", "variables": {"filter": {"attributes": [...]}}}
        resp = []
        for q in queries:
            attrs = (((q or {}).get("variables") or {}).get("filter") or {}).get("attributes", [])
            products = _response_for_filters(attrs)
            resp.append({"data": {"products": products}})

        out = json.dumps(resp).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

if __name__ == "__main__":
    print("Mock pricing API on http://127.0.0.1:4000/  (set PLANCOSTS_API_URL=http://127.0.0.1:4000)")
    print(f"MODE={MODE}  DEFAULT_PRICE={DEFAULT_PRICE}")
    for k, v in OVERRIDE.items():
        print(f"  {k}={v}")
    HTTPServer(("127.0.0.1", 4000), H).serve_forever()
