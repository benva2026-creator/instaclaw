#!/usr/bin/env python3
"""
InstaClaw - Production-ready SaaS platform with unified API, billing, and analytics
"""

import os
import json
import hashlib
import uuid
import bcrypt
import jwt
import stripe
import redis
import requests
from datetime import datetime, timedelta
from functools import wraps
from typing import Optional, Dict, Any

from flask import Flask, request, jsonify, render_template, session, redirect, url_for, flash
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_cors import CORS
import sqlite3
import openai
from anthropic import Anthropic
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'dev-secret-key-change-in-prod')
CORS(app)

# Initialize services (optional - app works without API keys)
if os.getenv('STRIPE_SECRET_KEY'):
    stripe.api_key = os.getenv('STRIPE_SECRET_KEY')
if os.getenv('OPENAI_API_KEY'):
    openai.api_key = os.getenv('OPENAI_API_KEY')

# Lazy initialize anthropic client to avoid startup issues
anthropic_client = None

def get_anthropic_client():
    """Lazy initialization of anthropic client"""
    global anthropic_client
    if anthropic_client is None and os.getenv('ANTHROPIC_API_KEY'):
        try:
            anthropic_client = Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
        except Exception as e:
            print(f"Warning: Failed to initialize Anthropic client: {e}")
            anthropic_client = False  # Mark as failed to avoid retry
    return anthropic_client if anthropic_client is not False else None

# Redis setup for rate limiting
try:
    redis_client = redis.Redis.from_url(os.getenv('REDIS_URL', 'redis://localhost:6379'))
    redis_client.ping()
except:
    redis_client = None
    print("Warning: Redis not available, using in-memory rate limiting")

# Rate limiter setup
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=os.getenv('REDIS_URL', 'memory://')
)
limiter.init_app(app)

# Subscription tiers and rate limits
SUBSCRIPTION_TIERS = {
    'free': {
        'tokens_per_month': 10000,
        'rate_limit': '100/hour',
        'price_per_month': 0,
        'stripe_price_id': None
    },
    'starter': {
        'tokens_per_month': 100000,
        'rate_limit': '1000/hour',
        'price_per_month': 9.99,
        'stripe_price_id': 'price_starter_monthly'
    },
    'pro': {
        'tokens_per_month': 1000000,
        'rate_limit': '5000/hour',
        'price_per_month': 49.99,
        'stripe_price_id': 'price_pro_monthly'
    },
    'enterprise': {
        'tokens_per_month': 10000000,
        'rate_limit': '20000/hour',
        'price_per_month': 199.99,
        'stripe_price_id': 'price_enterprise_monthly'
    }
}

# Database setup
def init_db():
    """Initialize database with enhanced schema"""
    print("Initializing database...")
    conn = sqlite3.connect('llm_gateway.db')
    c = conn.cursor()
    
    # Enhanced users table
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (id TEXT PRIMARY KEY, 
                  email TEXT UNIQUE,
                  password_hash TEXT,
                  api_key TEXT UNIQUE, 
                  subscription_tier TEXT DEFAULT 'free',
                  stripe_customer_id TEXT,
                  stripe_subscription_id TEXT,
                  tokens_included INTEGER, 
                  tokens_used INTEGER DEFAULT 0,
                  tokens_reset_date TEXT,
                  is_active BOOLEAN DEFAULT TRUE,
                  email_verified BOOLEAN DEFAULT FALSE,
                  created_at TEXT,
                  updated_at TEXT)''')
    
    # Enhanced usage tracking
    c.execute('''CREATE TABLE IF NOT EXISTS usage_logs
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  user_id TEXT, 
                  provider TEXT,
                  model TEXT, 
                  tokens INTEGER, 
                  cost REAL, 
                  endpoint TEXT,
                  response_time REAL,
                  timestamp TEXT,
                  FOREIGN KEY (user_id) REFERENCES users (id))''')
    
    # Analytics aggregations table
    c.execute('''CREATE TABLE IF NOT EXISTS analytics_daily
                 (date TEXT,
                  user_id TEXT,
                  total_requests INTEGER DEFAULT 0,
                  total_tokens INTEGER DEFAULT 0,
                  total_cost REAL DEFAULT 0,
                  avg_response_time REAL DEFAULT 0,
                  PRIMARY KEY (date, user_id))''')
    
    # Webhook events table
    c.execute('''CREATE TABLE IF NOT EXISTS webhook_events
                 (id TEXT PRIMARY KEY,
                  event_type TEXT,
                  user_id TEXT,
                  payload TEXT,
                  processed BOOLEAN DEFAULT FALSE,
                  created_at TEXT)''')
    
    # API Documentation requests
    c.execute('''CREATE TABLE IF NOT EXISTS api_docs_requests
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  endpoint TEXT,
                  method TEXT,
                  user_id TEXT,
                  timestamp TEXT)''')
    
    # Create demo user if not exists
    demo_key = "demo_" + hashlib.md5("demo".encode()).hexdigest()[:16]
    c.execute("SELECT * FROM users WHERE api_key = ?", (demo_key,))
    if not c.fetchone():
        user_id = str(uuid.uuid4())
        password_hash = bcrypt.hashpw("demo123".encode('utf-8'), bcrypt.gensalt())
        now = datetime.now().isoformat()
        reset_date = (datetime.now() + timedelta(days=30)).isoformat()
        
        c.execute("""INSERT INTO users 
                     (id, email, password_hash, api_key, subscription_tier, 
                      tokens_included, tokens_used, tokens_reset_date, created_at, updated_at)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                 (user_id, "demo@example.com", password_hash.decode('utf-8'), 
                  demo_key, "starter", 100000, 0, reset_date, now, now))
    
    conn.commit()
    conn.close()
    print("Database initialized successfully!")

# Initialize database
print("Starting InstaClaw...")
try:
    init_db()
    print("✅ Database initialized successfully!")
except Exception as e:
    print(f"⚠️  Database initialization warning: {e}")
    # Continue anyway - app can work without full database features

# Real API integrations
def call_openai_api(prompt: str, model: str = "gpt-3.5-turbo") -> Dict[str, Any]:
    """Real OpenAI API call"""
    if not openai.api_key:
        return call_openai_mock(prompt, model)
    
    try:
        start_time = datetime.now()
        response = openai.ChatCompletion.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500
        )
        end_time = datetime.now()
        
        tokens = response['usage']['total_tokens']
        cost = calculate_openai_cost(model, tokens)
        
        return {
            "response": response['choices'][0]['message']['content'],
            "tokens": tokens,
            "cost": cost,
            "model": model,
            "response_time": (end_time - start_time).total_seconds(),
            "provider": "openai"
        }
    except Exception as e:
        print(f"OpenAI API error: {e}")
        return call_openai_mock(prompt, model)

def call_anthropic_api(prompt: str, model: str = "claude-3-sonnet-20240229") -> Dict[str, Any]:
    """Real Anthropic API call"""
    client = get_anthropic_client()
    if not client:
        return call_claude_mock(prompt, model)
    
    try:
        start_time = datetime.now()
        message = client.messages.create(
            model=model,
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}]
        )
        end_time = datetime.now()
        
        tokens = message.usage.input_tokens + message.usage.output_tokens
        cost = calculate_anthropic_cost(model, tokens)
        
        return {
            "response": message.content[0].text,
            "tokens": tokens,
            "cost": cost,
            "model": model,
            "response_time": (end_time - start_time).total_seconds(),
            "provider": "anthropic"
        }
    except Exception as e:
        print(f"Anthropic API error: {e}")
        return call_claude_mock(prompt, model)

# Cost calculation functions
def calculate_openai_cost(model: str, tokens: int) -> float:
    """Calculate OpenAI API cost"""
    rates = {
        "gpt-4": 0.00003,
        "gpt-3.5-turbo": 0.000002,
        "gpt-4-turbo": 0.00001
    }
    return tokens * rates.get(model, 0.000002)

def calculate_anthropic_cost(model: str, tokens: int) -> float:
    """Calculate Anthropic API cost"""
    rates = {
        "claude-3-sonnet-20240229": 0.000015,
        "claude-3-haiku-20240307": 0.000001,
        "claude-3-opus-20240229": 0.000075
    }
    return tokens * rates.get(model, 0.000015)

# Mock functions for fallback
def call_openai_mock(prompt, model="gpt-3.5-turbo"):
    """Mock OpenAI API call"""
    tokens = len(prompt.split()) * 1.3
    response = f"[MOCK] This is a simulated response from {model} to: '{prompt[:50]}...'"
    cost = calculate_openai_cost(model, int(tokens))
    return {
        "response": response,
        "tokens": int(tokens),
        "cost": round(cost, 6),
        "model": model,
        "response_time": 0.5,
        "provider": "openai"
    }

def call_claude_mock(prompt, model="claude-3-sonnet-20240229"):
    """Mock Anthropic API call"""
    tokens = len(prompt.split()) * 1.2
    response = f"[MOCK] This is a simulated response from {model} to: '{prompt[:50]}...'"
    cost = calculate_anthropic_cost(model, int(tokens))
    return {
        "response": response,
        "tokens": int(tokens),
        "cost": round(cost, 6),
        "model": model,
        "response_time": 0.7,
        "provider": "anthropic"
    }

# Authentication and authorization
def generate_jwt(user_id: str) -> str:
    """Generate JWT token"""
    payload = {
        'user_id': user_id,
        'exp': datetime.utcnow() + timedelta(hours=24)
    }
    return jwt.encode(payload, os.getenv('JWT_SECRET_KEY', app.secret_key), algorithm='HS256')

def verify_jwt(token: str) -> Optional[str]:
    """Verify JWT token"""
    try:
        payload = jwt.decode(token, os.getenv('JWT_SECRET_KEY', app.secret_key), algorithms=['HS256'])
        return payload['user_id']
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

def require_api_key(f):
    """API key authentication decorator"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = request.headers.get('X-API-Key') or request.args.get('api_key')
        if not api_key:
            return jsonify({"error": "API key required"}), 401
        
        conn = sqlite3.connect('llm_gateway.db')
        c = conn.cursor()
        c.execute("""SELECT id, subscription_tier, tokens_included, tokens_used, 
                           tokens_reset_date, is_active FROM users WHERE api_key = ?""", (api_key,))
        user = c.fetchone()
        conn.close()
        
        if not user or not user[5]:  # user[5] is is_active
            return jsonify({"error": "Invalid or inactive API key"}), 401
        
        # Check if tokens need to be reset
        reset_date = datetime.fromisoformat(user[4])
        if datetime.now() > reset_date:
            # Reset tokens for new billing period
            conn = sqlite3.connect('llm_gateway.db')
            c = conn.cursor()
            new_reset_date = (datetime.now() + timedelta(days=30)).isoformat()
            c.execute("UPDATE users SET tokens_used = 0, tokens_reset_date = ? WHERE api_key = ?", 
                     (new_reset_date, api_key))
            conn.commit()
            conn.close()
            user = list(user)
            user[3] = 0  # tokens_used
        
        request.user_id, request.tier, request.tokens_included, request.tokens_used = user[0], user[1], user[2], user[3]
        return f(*args, **kwargs)
    return decorated_function

def require_login(f):
    """Login required decorator"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = session.get('jwt_token')
        if not token:
            return redirect(url_for('login'))
        
        user_id = verify_jwt(token)
        if not user_id:
            session.pop('jwt_token', None)
            return redirect(url_for('login'))
        
        request.current_user_id = user_id
        return f(*args, **kwargs)
    return decorated_function

# Rate limiting based on subscription tier
def get_rate_limit():
    """Get rate limit for current user"""
    api_key = request.headers.get('X-API-Key') or request.args.get('api_key')
    if not api_key:
        return "100/hour"  # Default limit
    
    conn = sqlite3.connect('llm_gateway.db')
    c = conn.cursor()
    c.execute("SELECT subscription_tier FROM users WHERE api_key = ?", (api_key,))
    tier = c.fetchone()
    conn.close()
    
    if tier:
        return SUBSCRIPTION_TIERS.get(tier[0], {}).get('rate_limit', '100/hour')
    return "100/hour"

# API Routes
@app.route('/api/chat', methods=['POST'])
@require_api_key
@limiter.limit(get_rate_limit)
def chat():
    """Enhanced unified chat endpoint"""
    data = request.get_json()
    prompt = data.get('prompt', '')
    model = data.get('model', 'auto')
    provider = data.get('provider', 'auto')
    
    if not prompt:
        return jsonify({"error": "Prompt required"}), 400
    
    # Check quota
    if request.tokens_used >= request.tokens_included:
        return jsonify({
            "error": "Token quota exceeded. Please upgrade your subscription.",
            "quota_exceeded": True,
            "upgrade_url": "/billing"
        }), 429
    
    # Route to appropriate provider/model
    if provider == 'openai' or (provider == 'auto' and model.startswith('gpt')):
        result = call_openai_api(prompt, model if model != 'auto' else 'gpt-3.5-turbo')
    elif provider == 'anthropic' or (provider == 'auto' and model.startswith('claude')):
        result = call_anthropic_api(prompt, model if model != 'auto' else 'claude-3-sonnet-20240229')
    else:
        # Auto-routing based on cost/performance
        result = call_openai_api(prompt, 'gpt-3.5-turbo')  # Default to cost-effective option
    
    # Log usage
    conn = sqlite3.connect('llm_gateway.db')
    c = conn.cursor()
    
    # Insert detailed usage log
    c.execute("""INSERT INTO usage_logs 
                 (user_id, provider, model, tokens, cost, endpoint, response_time, timestamp)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
             (request.user_id, result['provider'], result['model'], result['tokens'], 
              result['cost'], '/api/chat', result['response_time'], datetime.now().isoformat()))
    
    # Update user token usage
    new_usage = request.tokens_used + result['tokens']
    c.execute("UPDATE users SET tokens_used = ?, updated_at = ? WHERE id = ?", 
             (new_usage, datetime.now().isoformat(), request.user_id))
    
    # Update daily analytics
    today = datetime.now().strftime('%Y-%m-%d')
    c.execute("""INSERT OR REPLACE INTO analytics_daily 
                 (date, user_id, total_requests, total_tokens, total_cost, avg_response_time)
                 VALUES (?, ?, 
                         COALESCE((SELECT total_requests FROM analytics_daily WHERE date = ? AND user_id = ?), 0) + 1,
                         COALESCE((SELECT total_tokens FROM analytics_daily WHERE date = ? AND user_id = ?), 0) + ?,
                         COALESCE((SELECT total_cost FROM analytics_daily WHERE date = ? AND user_id = ?), 0) + ?,
                         ?)""",
             (today, request.user_id, today, request.user_id, today, request.user_id, 
              result['tokens'], today, request.user_id, result['cost'], result['response_time']))
    
    conn.commit()
    conn.close()
    
    return jsonify({
        "response": result['response'],
        "model_used": result['model'],
        "provider": result['provider'],
        "tokens_used": result['tokens'],
        "cost": result['cost'],
        "response_time": result['response_time'],
        "total_tokens_used": new_usage,
        "remaining_quota": max(0, request.tokens_included - new_usage),
        "quota_percentage": min(100, (new_usage / request.tokens_included) * 100)
    })

# Authentication routes
@app.route('/auth/register', methods=['GET', 'POST'])
def register():
    """User registration"""
    if request.method == 'POST':
        data = request.get_json() if request.is_json else request.form
        email = data.get('email', '').lower().strip()
        password = data.get('password', '')
        
        if not email or not password:
            if request.is_json:
                return jsonify({"error": "Email and password required"}), 400
            flash("Email and password required")
            return render_template('auth/register.html')
        
        # Check if user exists
        conn = sqlite3.connect('llm_gateway.db')
        c = conn.cursor()
        c.execute("SELECT id FROM users WHERE email = ?", (email,))
        if c.fetchone():
            conn.close()
            if request.is_json:
                return jsonify({"error": "Email already registered"}), 400
            flash("Email already registered")
            return render_template('auth/register.html')
        
        # Create user
        user_id = str(uuid.uuid4())
        password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
        api_key = "sk_" + hashlib.md5((email + str(datetime.now())).encode()).hexdigest()
        now = datetime.now().isoformat()
        reset_date = (datetime.now() + timedelta(days=30)).isoformat()
        
        c.execute("""INSERT INTO users 
                     (id, email, password_hash, api_key, subscription_tier, 
                      tokens_included, tokens_used, tokens_reset_date, created_at, updated_at)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                 (user_id, email, password_hash.decode('utf-8'), api_key, 
                  "free", SUBSCRIPTION_TIERS["free"]["tokens_per_month"], 0, reset_date, now, now))
        conn.commit()
        conn.close()
        
        if request.is_json:
            return jsonify({"message": "Registration successful", "api_key": api_key}), 201
        
        # Auto-login after registration
        token = generate_jwt(user_id)
        session['jwt_token'] = token
        flash("Registration successful! Welcome to InstaClaw.")
        return redirect(url_for('dashboard'))
    
    return render_template('auth/register.html')

@app.route('/auth/login', methods=['GET', 'POST'])
def login():
    """User login"""
    if request.method == 'POST':
        data = request.get_json() if request.is_json else request.form
        email = data.get('email', '').lower().strip()
        password = data.get('password', '')
        
        if not email or not password:
            if request.is_json:
                return jsonify({"error": "Email and password required"}), 400
            flash("Email and password required")
            return render_template('auth/login.html')
        
        # Verify user
        conn = sqlite3.connect('llm_gateway.db')
        c = conn.cursor()
        c.execute("SELECT id, password_hash, is_active FROM users WHERE email = ?", (email,))
        user = c.fetchone()
        conn.close()
        
        if not user or not bcrypt.checkpw(password.encode('utf-8'), user[1].encode('utf-8')):
            if request.is_json:
                return jsonify({"error": "Invalid credentials"}), 401
            flash("Invalid email or password")
            return render_template('auth/login.html')
        
        if not user[2]:  # is_active
            if request.is_json:
                return jsonify({"error": "Account deactivated"}), 401
            flash("Account has been deactivated")
            return render_template('auth/login.html')
        
        token = generate_jwt(user[0])
        if request.is_json:
            return jsonify({"token": token}), 200
        
        session['jwt_token'] = token
        return redirect(url_for('dashboard'))
    
    return render_template('auth/login.html')

@app.route('/auth/logout')
def logout():
    """User logout"""
    session.pop('jwt_token', None)
    flash("Logged out successfully")
    return redirect(url_for('login'))

# Stripe billing integration
@app.route('/billing')
@require_login
def billing():
    """Billing dashboard"""
    conn = sqlite3.connect('llm_gateway.db')
    c = conn.cursor()
    c.execute("""SELECT subscription_tier, stripe_customer_id, stripe_subscription_id, 
                        tokens_included, tokens_used, tokens_reset_date 
                 FROM users WHERE id = ?""", (request.current_user_id,))
    user_data = c.fetchone()
    conn.close()
    
    return render_template('billing.html', 
                         user_data=user_data,
                         subscription_tiers=SUBSCRIPTION_TIERS,
                         stripe_pk=os.getenv('STRIPE_PUBLISHABLE_KEY'))

@app.route('/create-checkout-session', methods=['POST'])
@require_login
def create_checkout_session():
    """Create Stripe checkout session"""
    data = request.get_json()
    tier = data.get('tier')
    
    if tier not in SUBSCRIPTION_TIERS:
        return jsonify({"error": "Invalid subscription tier"}), 400
    
    try:
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price': SUBSCRIPTION_TIERS[tier]['stripe_price_id'],
                'quantity': 1,
            }],
            mode='subscription',
            success_url=url_for('billing_success', _external=True),
            cancel_url=url_for('billing', _external=True),
            client_reference_id=request.current_user_id,
        )
        return jsonify({'checkout_url': checkout_session.url})
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/billing/success')
@require_login
def billing_success():
    """Billing success page"""
    flash("Subscription updated successfully!")
    return redirect(url_for('billing'))

@app.route('/webhook/stripe', methods=['POST'])
def stripe_webhook():
    """Handle Stripe webhooks"""
    payload = request.data
    sig_header = request.headers.get('Stripe-Signature')
    
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, os.getenv('STRIPE_WEBHOOK_SECRET')
        )
    except ValueError:
        return '', 400
    except stripe.error.SignatureVerificationError:
        return '', 400
    
    # Handle different event types
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        user_id = session['client_reference_id']
        
        # Update user subscription
        conn = sqlite3.connect('llm_gateway.db')
        c = conn.cursor()
        
        # Get subscription details from Stripe
        subscription = stripe.Subscription.retrieve(session['subscription'])
        price_id = subscription['items']['data'][0]['price']['id']
        
        # Map price_id to tier
        tier = None
        for tier_name, tier_data in SUBSCRIPTION_TIERS.items():
            if tier_data.get('stripe_price_id') == price_id:
                tier = tier_name
                break
        
        if tier:
            c.execute("""UPDATE users SET subscription_tier = ?, 
                                          stripe_customer_id = ?,
                                          stripe_subscription_id = ?,
                                          tokens_included = ?,
                                          updated_at = ?
                         WHERE id = ?""",
                     (tier, session['customer'], session['subscription'],
                      SUBSCRIPTION_TIERS[tier]['tokens_per_month'],
                      datetime.now().isoformat(), user_id))
            conn.commit()
        conn.close()
    
    # Log webhook event
    conn = sqlite3.connect('llm_gateway.db')
    c = conn.cursor()
    c.execute("INSERT INTO webhook_events (id, event_type, payload, created_at) VALUES (?, ?, ?, ?)",
             (event['id'], event['type'], json.dumps(event['data']), datetime.now().isoformat()))
    conn.commit()
    conn.close()
    
    return '', 200

# Analytics dashboard
@app.route('/analytics')
@require_login
def analytics():
    """Analytics dashboard"""
    conn = sqlite3.connect('llm_gateway.db')
    c = conn.cursor()
    
    # Get user analytics
    c.execute("""SELECT date, total_requests, total_tokens, total_cost, avg_response_time
                 FROM analytics_daily 
                 WHERE user_id = ? 
                 ORDER BY date DESC LIMIT 30""", (request.current_user_id,))
    daily_stats = c.fetchall()
    
    # Get model usage breakdown
    c.execute("""SELECT model, COUNT(*) as requests, SUM(tokens) as tokens, SUM(cost) as cost
                 FROM usage_logs 
                 WHERE user_id = ? AND timestamp >= date('now', '-30 days')
                 GROUP BY model
                 ORDER BY requests DESC""", (request.current_user_id,))
    model_stats = c.fetchall()
    
    # Get recent usage
    c.execute("""SELECT model, tokens, cost, timestamp, response_time
                 FROM usage_logs 
                 WHERE user_id = ? 
                 ORDER BY timestamp DESC LIMIT 50""", (request.current_user_id,))
    recent_usage = c.fetchall()
    
    conn.close()
    
    return render_template('analytics.html', 
                         daily_stats=daily_stats,
                         model_stats=model_stats,
                         recent_usage=recent_usage)

# API Documentation
@app.route('/docs')
def api_docs():
    """API documentation"""
    return render_template('api_docs.html')

@app.route('/docs/api')
def api_docs_json():
    """OpenAPI specification"""
    spec = {
        "openapi": "3.0.0",
        "info": {
            "title": "InstaClaw API",
            "version": "1.0.0",
            "description": "Unified API for accessing multiple LLM providers"
        },
        "servers": [
            {"url": request.url_root, "description": "Production server"}
        ],
        "paths": {
            "/api/chat": {
                "post": {
                    "summary": "Generate text completion",
                    "parameters": [
                        {
                            "name": "X-API-Key",
                            "in": "header",
                            "required": True,
                            "schema": {"type": "string"}
                        }
                    ],
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "prompt": {"type": "string"},
                                        "model": {"type": "string", "default": "auto"},
                                        "provider": {"type": "string", "default": "auto"}
                                    },
                                    "required": ["prompt"]
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    return jsonify(spec)

# Web Interface Routes
@app.route('/')
def dashboard():
    """Enhanced dashboard"""
    if 'jwt_token' not in session:
        return redirect(url_for('login'))
    
    user_id = verify_jwt(session['jwt_token'])
    if not user_id:
        session.pop('jwt_token', None)
        return redirect(url_for('login'))
    
    conn = sqlite3.connect('llm_gateway.db')
    c = conn.cursor()
    
    # Get user info
    c.execute("""SELECT email, subscription_tier, tokens_included, tokens_used, 
                        tokens_reset_date, api_key FROM users WHERE id = ?""", (user_id,))
    user_data = c.fetchone()
    
    # Get recent usage stats
    c.execute("""SELECT COUNT(*) as requests, SUM(tokens) as tokens, SUM(cost) as cost
                 FROM usage_logs 
                 WHERE user_id = ? AND timestamp >= date('now', '-7 days')""", (user_id,))
    weekly_stats = c.fetchone()
    
    # Get model breakdown
    c.execute("""SELECT model, COUNT(*) as requests
                 FROM usage_logs 
                 WHERE user_id = ? AND timestamp >= date('now', '-7 days')
                 GROUP BY model
                 ORDER BY requests DESC LIMIT 5""", (user_id,))
    model_breakdown = c.fetchall()
    
    conn.close()
    
    return render_template('dashboard.html', 
                         user_data=user_data,
                         weekly_stats=weekly_stats,
                         model_breakdown=model_breakdown,
                         subscription_tiers=SUBSCRIPTION_TIERS)

@app.route('/test')
@require_login
def test_interface():
    """Enhanced test interface"""
    return render_template('test.html')

@app.route('/admin')
def admin():
    """Enhanced admin panel"""
    # Simple admin check - in production, use proper role-based auth
    if not session.get('jwt_token'):
        return redirect(url_for('login'))
    
    conn = sqlite3.connect('llm_gateway.db')
    c = conn.cursor()
    
    # Get system stats
    c.execute("SELECT COUNT(*) FROM users")
    total_users = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM usage_logs WHERE timestamp >= date('now', '-1 day')")
    daily_requests = c.fetchone()[0]
    
    c.execute("SELECT SUM(cost) FROM usage_logs WHERE timestamp >= date('now', '-1 day')")
    daily_revenue = c.fetchone()[0] or 0
    
    # Get all users
    c.execute("""SELECT id, email, subscription_tier, tokens_included, tokens_used, 
                        created_at, is_active FROM users ORDER BY created_at DESC LIMIT 50""")
    users = c.fetchall()
    
    # Get recent usage
    c.execute("""SELECT u.email, ul.model, ul.tokens, ul.cost, ul.timestamp 
                 FROM usage_logs ul 
                 JOIN users u ON ul.user_id = u.id 
                 ORDER BY ul.timestamp DESC LIMIT 100""")
    usage = c.fetchall()
    
    conn.close()
    
    return render_template('admin.html', 
                         users=users, 
                         usage=usage,
                         total_users=total_users,
                         daily_requests=daily_requests,
                         daily_revenue=daily_revenue)

# New InstaClaw Platform Routes
@app.route('/endpoints')
@require_login
def endpoints():
    """All OpenClaw endpoints page"""
    return render_template('endpoints.html')

@app.route('/integrations')
@require_login
def integrations():
    """Integrations management page"""
    return render_template('integrations.html')

@app.route('/safeguards')
@require_login
def safeguards():
    """SafeGuards configuration page"""
    return render_template('safeguards.html')

@app.route('/skills')
@require_login
def skills_marketplace():
    """Skills marketplace page"""
    return render_template('skills_marketplace.html')

@app.route('/community')
@require_login
def community():
    """Community page"""
    return render_template('community.html')

@app.route('/api/openclaw', methods=['POST'])
@require_api_key
@limiter.limit("100 per hour")
def openclaw_unified():
    """Unified OpenClaw API endpoint"""
    data = request.get_json()
    
    if not data or 'tools' not in data:
        return jsonify({"error": "Tools array required"}), 400
    
    results = []
    total_tokens = 0
    total_cost = 0
    
    for tool_request in data['tools']:
        tool_name = tool_request.get('tool')
        if not tool_name:
            continue
            
        # Mock execution - in production this would route to actual OpenClaw tools
        mock_result = {
            "tool": tool_name,
            "success": True,
            "data": f"Mock result from {tool_name}",
            "tokens": 10,
            "cost": 0.0001
        }
        
        results.append(mock_result)
        total_tokens += mock_result['tokens']
        total_cost += mock_result['cost']
    
    # Log usage
    conn = sqlite3.connect('llm_gateway.db')
    c = conn.cursor()
    c.execute("INSERT INTO usage_logs (user_id, provider, model, tokens, cost, endpoint, response_time, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
             (request.user_id, "openclaw", "unified-api", total_tokens, total_cost, "openclaw_unified", 1.2, datetime.now().isoformat()))
    
    # Update user token usage
    c.execute("UPDATE users SET tokens_used = tokens_used + ? WHERE id = ?", 
              (total_tokens, request.user_id))
    
    conn.commit()
    conn.close()
    
    return jsonify({
        "results": results,
        "execution_time": 1.2,
        "tokens_used": total_tokens,
        "cost": total_cost
    })

# Health check endpoint
@app.route('/health')
def health_check():
    """Health check endpoint - simple and reliable for deployment"""
    try:
        # Simple health check that doesn't depend on database
        return jsonify({
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "version": "1.0.0",
            "environment": os.getenv('RAILWAY_ENVIRONMENT', 'local')
        }), 200
    except Exception as e:
        return jsonify({
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }), 500

# Simple ping endpoint for basic connectivity
@app.route('/ping')
def ping():
    """Ultra-simple ping endpoint"""
    return "pong", 200

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    host = os.getenv('HOST', '0.0.0.0')
    debug = os.getenv('DEBUG', 'False').lower() == 'true'
    print(f"Starting Flask app on {host}:{port}")
    app.run(host=host, port=port, debug=debug)