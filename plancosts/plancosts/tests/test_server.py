import json
from http.server import BaseHTTPRequestHandler, HTTPServer


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        try:
            queries = json.loads(body.decode("utf-8"))
            if not isinstance(queries, list):
                queries = [queries]
        except Exception:
            queries = []

        # Return one result per query, each with a USD price.
        # Use a deterministic price so it’s easy to eyeball (e.g. 0.0100, 0.0200, ...).
        results = []
        for i, _ in enumerate(queries, start=1):
            results.append(
                {
                    "data": {
                        "products": [
                            {
                                "onDemandPricing": [
                                    {
                                        "priceDimensions": [
                                            {"pricePerUnit": {"USD": f"{i/100:.4f}"}}
                                        ]
                                    }
                                ]
                            }
                        ]
                    }
                }
            )

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(results).encode("utf-8"))


if __name__ == "__main__":
    print("Mock price API on http://localhost:4000/graphql")
    HTTPServer(("127.0.0.1", 4000), Handler).serve_forever()
