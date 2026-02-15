# One-Click Deploy to Railway

Once you push this to GitHub, add this deploy button to your README:

```markdown
[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/template/your-template-id)
```

Or use this direct deploy URL:
https://railway.app/new/template?template=https://github.com/[username]/instaclaw

## Environment Variables for Railway:
- `FLASK_SECRET_KEY`: Generate with `openssl rand -base64 32`  
- `DEBUG`: `False`
- `FLASK_ENV`: `production`

Railway will automatically:
- Detect Python app
- Install dependencies from requirements.txt  
- Run with gunicorn
- Provide HTTPS domain
- Handle port binding