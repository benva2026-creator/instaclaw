# InstaClaw Deployment Guide

## Quick Deploy Options

### Option 1: Railway (Recommended)
1. Go to [railway.app](https://railway.app)
2. Sign up/login with GitHub
3. Click "New Project" → "Deploy from GitHub repo"
4. Connect this repository
5. Railway will auto-detect Python and deploy
6. Set environment variables:
   - `FLASK_SECRET_KEY=your-secret-key`
   - `DEBUG=False`

### Option 2: Render
1. Go to [render.com](https://render.com)  
2. Sign up and create new "Web Service"
3. Connect GitHub repository
4. Build command: `pip install -r requirements.txt`
5. Start command: `gunicorn app:app`

### Option 3: Heroku
```bash
# Install Heroku CLI first
heroku create instaclaw-demo
git push heroku main
heroku open
```

## Environment Variables Needed
- `FLASK_SECRET_KEY`: Random secret key
- `DEBUG`: Set to `False` for production  
- `PORT`: Automatically set by hosting service
- `DATABASE_URL`: Will use SQLite by default

## Local Development
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Access at: http://localhost:5000