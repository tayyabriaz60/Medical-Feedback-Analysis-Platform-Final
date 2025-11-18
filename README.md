# Medical Feedback Analysis Platform

AI-powered medical feedback analysis system using Gemini AI.

## Features

- 📝 Patient feedback submission
- 🤖 AI analysis with Gemini
- 📊 Staff dashboard
- ⚠️ Urgent alerts
- 📈 Analytics

## Tech Stack

- **Backend:** FastAPI, SQLAlchemy, AsyncPG
- **Database:** PostgreSQL
- **AI:** Google Gemini API
- **Frontend:** HTML, JavaScript
- **Deployment:** Render

## Setup

### Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Setup environment
cp env.example .env
# Edit .env with your values

# Run
uvicorn app.main:asgi_app --reload
```

### Render Deployment

1. Push to GitHub
2. Connect GitHub to Render
3. Set environment variables
4. Deploy

## Environment Variables

```
SECRET_KEY=your_secret_key
GOOGLE_API_KEY=your_google_api_key
DATABASE_URL=postgresql://user:pass@host/db
ADMIN_EMAIL=admin@hospital.org
ADMIN_PASSWORD=your_password
ENVIRONMENT=production
```

## API Endpoints

- `POST /feedback` - Submit feedback
- `GET /feedback/all` - Get all feedback
- `POST /auth/login` - Login
- `POST /auth/register` - Register
- `/docs` - API documentation

## License

MIT

