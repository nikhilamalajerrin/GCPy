# mock_pricing_api.py
from http.server import BaseHTTPRequestHandler, HTTPServer
import json

class H(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8")
        try:
            queries = json.loads(body)
            if not isinstance(queries, list):
                queries = [queries]
        except Exception:
            queries = []

        # Always return the same price so your multipliers (GB, IOPS, instance count) create the totals you saw.
        resp = [{
            "data": {
                "products": [{
                    "onDemandPricing": [{
                        "priceDimensions": [{
                            "pricePerUnit": {"USD": "0.0416"}
                        }]
                    }]
                }]
            }
        } for _ in queries]

        out = json.dumps(resp).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

if __name__ == "__main__":
    print("Mock pricing API on http://127.0.0.1:4000/")
    HTTPServer(("127.0.0.1", 4000), H).serve_forever()
