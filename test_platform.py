#!/usr/bin/env python3
"""
InstaClaw Platform Test Suite
Tests all major functionality of the platform
"""

import requests
import json
import time
import sys

BASE_URL = "http://localhost:5000"
API_KEY = "demo_fe01ce2a7fbac8fa"

def test_health_check():
    """Test basic health endpoint"""
    print("🔍 Testing health check...")
    response = requests.get(f"{BASE_URL}/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    print("✅ Health check passed")

def test_unified_api():
    """Test the unified OpenClaw API endpoint"""
    print("🔍 Testing unified OpenClaw API...")
    
    payload = {
        "tools": [
            {"tool": "web_search", "query": "OpenClaw AI automation"},
            {"tool": "weather", "location": "San Francisco"},
            {"tool": "gmail", "action": "list_emails", "limit": 5}
        ]
    }
    
    headers = {
        "X-API-Key": API_KEY,
        "Content-Type": "application/json"
    }
    
    response = requests.post(f"{BASE_URL}/api/openclaw", json=payload, headers=headers)
    assert response.status_code == 200
    
    data = response.json()
    assert "results" in data
    assert len(data["results"]) == 3
    assert "tokens_used" in data
    assert "cost" in data
    
    print("✅ Unified API test passed")

def test_page_accessibility():
    """Test that all main pages are accessible (redirects to login expected)"""
    print("🔍 Testing page accessibility...")
    
    pages = [
        "/",
        "/endpoints", 
        "/integrations",
        "/safeguards",
        "/skills",
        "/community",
        "/dashboard",
        "/test",
        "/admin",
        "/auth/login",
        "/auth/register"
    ]
    
    for page in pages:
        response = requests.get(f"{BASE_URL}{page}")
        # Most pages should either return 200 (login/register) or 302 (redirect to login)
        assert response.status_code in [200, 302], f"Page {page} returned {response.status_code}"
        print(f"✅ Page {page} accessible")

def test_api_key_validation():
    """Test API key validation"""
    print("🔍 Testing API key validation...")
    
    # Test with invalid API key
    headers = {
        "X-API-Key": "invalid_key",
        "Content-Type": "application/json"
    }
    
    payload = {"tools": [{"tool": "web_search", "query": "test"}]}
    
    response = requests.post(f"{BASE_URL}/api/openclaw", json=payload, headers=headers)
    assert response.status_code == 401
    
    # Test with missing API key
    response = requests.post(f"{BASE_URL}/api/openclaw", json=payload)
    assert response.status_code == 401
    
    print("✅ API key validation working")

def run_all_tests():
    """Run all tests"""
    print("🚀 Starting InstaClaw Platform Test Suite\n")
    
    try:
        test_health_check()
        test_unified_api()
        test_page_accessibility() 
        test_api_key_validation()
        
        print("\n🎉 All tests passed! InstaClaw platform is working correctly.")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_all_tests()