# InstaClaw - Unified AI API Gateway

A production-ready unified AI API gateway that routes requests to multiple providers with subscription billing and usage tracking.

## Features

- **Unified API**: Single endpoint for multiple LLM providers (OpenAI, Anthropic, etc.)
- **Smart Routing**: Route to cheapest or best-performing model based on preference
- **Usage Tracking**: Real-time token and cost tracking with quotas
- **Subscription Billing**: Tier-based pricing with overage fees
- **Web Dashboard**: Visual interface to monitor usage and test the API
- **Admin Panel**: User management and analytics

## Quick Start

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Run the app:
   ```bash
   python app.py
   ```

3. Open your browser to:
   - Dashboard: http://localhost:5000
   - Test Interface: http://localhost:5000/test
   - Admin Panel: http://localhost:5000/admin

## API Usage

```bash
curl -X POST http://localhost:5000/api/chat \
  -H "X-API-Key: demo_a665a45920422f9d" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Hello!", "preference": "cost"}'
```

## Demo Features

- Pre-loaded demo user with API key
- Mock LLM responses (no real API calls)
- SQLite database for persistence
- Real-time usage tracking
- Visual dashboards and analytics

## Architecture

- **Flask** web framework
- **SQLite** for user/usage data
- **Tailwind CSS** + **Alpine.js** for UI
- Mock integrations with OpenAI/Anthropic APIs
- Token-based authentication