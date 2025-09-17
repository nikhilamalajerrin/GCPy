#!/usr/bin/env python3
"""Mock pricing server for testing."""
from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route('/', methods=['POST'])
def pricing_api():
    """Mock pricing API endpoint."""
    queries = request.json
    results = []
    
    for query in queries:
        # Return mock pricing data
        results.append({
            "data": {
                "products": [{
                    "onDemandPricing": [{
                        "priceDimensions": [{
                            "unit": "Hrs",
                            "pricePerUnit": {
                                "USD": "0.0416"  # Mock price for m5.large
                            }
                        }]
                    }]
                }]
            }
        })
    
    return jsonify(results)

if __name__ == '__main__':
    app.run(port=4000)