# Stage 1: Build frontend
FROM node:20-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci --no-audit
COPY frontend/ ./
RUN npm run build

# Stage 2: Python backend + built frontend
FROM python:3.12-slim
WORKDIR /app

# Install Python dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY backend/ ./backend/

# Copy built frontend from stage 1
COPY --from=frontend-build /app/frontend/dist/ ./frontend/dist/

# Environment
# DEMO_MODE disables real deployment (safe for a hosted demo). Set DEFAULT_PROJECT
# to a project ID if you want the demo to pre-fill one; leave empty otherwise.
ENV DEMO_MODE=true
ENV DEFAULT_PROJECT=""
ENV PORT=8080

EXPOSE 8080

CMD ["python3", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080", "--app-dir", "backend"]
