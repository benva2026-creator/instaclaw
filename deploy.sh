#!/bin/bash
echo "🦞 InstaClaw Deployment Script"
echo "=============================="

# Check if remote already exists
if git remote get-url origin > /dev/null 2>&1; then
    echo "GitHub remote already configured"
else
    echo "Adding GitHub remote..."
    git remote add origin https://github.com/benva2026-creator/instaclaw.git
fi

# Ensure we're on main branch
echo "Setting up main branch..."
git branch -M main

# Try to push with GitHub CLI first, then fallback to manual
echo "Pushing code to GitHub..."
if command -v gh &> /dev/null && gh auth status &> /dev/null; then
    echo "Using GitHub CLI..."
    git push -u origin main
elif git push -u origin main 2>/dev/null; then
    echo "✅ Push successful!"
else
    echo "❌ Authentication needed. Please run:"
    echo "gh auth login"
    echo "Then run this script again."
    echo ""
    echo "OR manually enter your GitHub credentials when prompted:"
    git push -u origin main
fi

echo ""
echo "✅ Code pushed to GitHub!"
echo ""
echo "🚀 Next: Deploy to Railway"
echo "=========================="
echo "1. Go to https://railway.app"
echo "2. Sign in with GitHub"
echo "3. Click 'New Project' → 'Deploy from GitHub repo'"  
echo "4. Select 'benva2026-creator/instaclaw'"
echo "5. Add these environment variables:"
echo "   - FLASK_SECRET_KEY = $(openssl rand -base64 32)"
echo "   - DEBUG = False"
echo ""
echo "🌐 Your InstaClaw will be live at:"
echo "   https://instaclaw-production-[random].up.railway.app"
echo ""
echo "📂 Repository: https://github.com/benva2026-creator/instaclaw"