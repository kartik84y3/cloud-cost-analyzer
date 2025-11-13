import os
import json
from flask import Flask, request, jsonify, send_from_directory, render_template_string
from decimal import Decimal, ROUND_HALF_UP

# optional Azure OpenAI imports
try:
    from azure.ai.openai import OpenAIClient
    from azure.core.credentials import AzureKeyCredential
    AZURE_OPENAI_AVAILABLE = True
except Exception:
    AZURE_OPENAI_AVAILABLE = False

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DATA_DIR = os.path.join(BASE_DIR, 'data')
FRONTEND_DIR = os.path.join(BASE_DIR, '..', 'frontend')

app = Flask(__name__, static_folder=FRONTEND_DIR, template_folder=FRONTEND_DIR)

PRICING_FILE = os.path.join(DATA_DIR, 'pricing.json')

def load_pricing():
    with open(PRICING_FILE, 'r') as f:
        return json.load(f)

def decimal(val):
    return float(Decimal(val).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))

@app.route('/')
def index():
    return app.send_static_file('index.html')

@app.route('/data/pricing.json')
def pricing_json():
    return send_from_directory(DATA_DIR, 'pricing.json')

@app.route('/api/calc', methods=['POST'])
def api_calc():
    payload = request.get_json() or {}
    resources = payload.get('resources', [])
    pricing = load_pricing()
    items = []
    total = 0.0

    for r in resources:
        t = r.get('type')
        sku = r.get('sku')
        region = r.get('region', 'eastus')
        qty = float(r.get('quantity', 1))
        hours = float(r.get('hours_per_month', 720))

        cost = 0.0
        # VM hourly pricing
        if t == 'vm':
            unit = pricing.get('vm', {}).get(sku, {}).get('hourly')
            if unit is None:
                unit = 0.0
            region_mult = pricing.get('region_multipliers', {}).get(region, 1.0)
            cost = unit * hours * qty * region_mult

        # storage monthly pricing per GB
        elif t == 'storage':
            unit = pricing.get('storage', {}).get(sku, {}).get('monthly_per_gb', 0.0)
            # For storage, we interpret 'quantity' as GB
            cost = unit * qty * (1.0) * pricing.get('region_multipliers', {}).get(region, 1.0)

        # sqldb monthly
        elif t == 'sqldb':
            unit = pricing.get('sqldb', {}).get(sku, {}).get('monthly', 0.0)
            cost = unit * qty * pricing.get('region_multipliers', {}).get(region, 1.0)

        cost = decimal(cost)
        items.append({
            'type': t,
            'sku': sku,
            'region': region,
            'quantity': qty,
            'hours_per_month': hours,
            'cost': cost
        })
        total += cost

    total = decimal(total)

    # Build basic optimization hints (rules-based)
    hints = []
    savings_estimate = 0.0
    for it in items:
        if it['type'] == 'vm':
            # example rule: if hours < 200 suggest auto-shutdown
            if it['hours_per_month'] < 200:
                hints.append({
                    'sku': it['sku'],
                    'type': it['type'],
                    'suggestion': 'This VM runs for few hours/month — consider auto-shutdown or schedule to save costs.',
                    'estimated_savings_percent': 15
                })
            # big vm -> suggest spot/reserved
            if it['sku'].lower().startswith('standard_d'):
                hints.append({
                    'sku': it['sku'],
                    'suggestion': 'Consider Reserved Instances for 1- or 3-year terms if this VM is long-running; or Spot VMs for non-critical batch jobs.',
                    'estimated_savings_percent': 30
                })
        if it['type'] == 'storage':
            # example: if storage > 100 GB suggest cool tier
            if it['quantity'] > 100:
                hints.append({
                    'sku': it['sku'],
                    'suggestion': 'Large storage detected — consider Cool or Archive lifecycle policies to save costs.',
                    'estimated_savings_percent': 20
                })

    # rough aggregate savings estimate
    if hints:
        # naive: average of hints' percents applied to total
        avg_pct = sum(h.get('estimated_savings_percent',0) for h in hints)/len(hints)
        savings_estimate = decimal(total * (avg_pct/100))
    else:
        savings_estimate = 0.0

    ai_summary = None
    # Call Azure OpenAI if configured (optional)
    if AZURE_OPENAI_AVAILABLE and os.getenv('OPENAI_ENDPOINT') and os.getenv('OPENAI_KEY') and os.getenv('OPENAI_DEPLOYMENT'):
        try:
            client = OpenAIClient(os.getenv('OPENAI_ENDPOINT'), AzureKeyCredential(os.getenv('OPENAI_KEY')))
            # Build compact prompt
            prompt = {
                "total": total,
                "items": items,
                "hints": hints,
                "savings_estimate": savings_estimate
            }
            messages = [
                {"role":"system","content":"You are an Azure cost advisor. Provide a short 3-sentence summary of cost and 3 concise actionable recommendations. Include approximate percent savings where possible."},
                {"role":"user","content":f"Analyze this JSON and return a short summary and 3 bullet recommendations: {json.dumps(prompt)}"}
            ]
            resp = client.get_chat_completions(deployment_name=os.getenv('OPENAI_DEPLOYMENT'),
                                              messages=messages,
                                              max_tokens=300)
            ai_summary = resp.choices[0].message.content.strip()
        except Exception as e:
            app.logger.warning("OpenAI call failed: %s", str(e))
            ai_summary = None

    response = {
        'items': items,
        'total': total,
        'hints': hints,
        'savings_estimate': savings_estimate,
        'ai_summary': ai_summary
    }
    return jsonify(response)

if __name__ == '__main__':
    # For local dev only; use proper WSGI on production
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=True)
