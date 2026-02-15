#!/bin/bash
echo "🦞 InstaClaw Deployment Script"
echo "=============================="

# Add GitHub remote and push to repository
echo "Adding GitHub remote and pushing code..."
git remote add origin https://github.com/benva2026-creator/instaclaw.git
git branch -M main
git push -u origin main

echo "✅ Code pushed to GitHub successfully!"
echo ""
echo "Next steps:"
echo "1. Go to https://railway.app"
echo "2. Sign in with GitHub" 
echo "3. Click 'New Project' → 'Deploy from GitHub repo'"
echo "4. Select 'benva2026-creator/instaclaw' repository"
echo "5. Add environment variables:"
echo "   - FLASK_SECRET_KEY = $(openssl rand -base64 32)"
echo "   - DEBUG = False"
echo "6. Your app will be live in ~2 minutes!"
echo ""
echo "🚀 InstaClaw will be available at: https://instaclaw-production-[random].up.railway.app"
echo ""
echo "Repository URL: https://github.com/benva2026-creator/instaclaw"