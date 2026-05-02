# Finances Dashboard

## Levantar la DB
```bash
docker-compose up -d
```

## Backend
```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

python manage.py migrate
python manage.py createsuperuser  # opcional, para /admin
python manage.py runserver
```
API disponible en http://localhost:8000/api/

## Frontend
```bash
cd frontend
npm install
npm run dev
```
UI disponible en http://localhost:5173/
