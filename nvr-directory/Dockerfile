FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY static ./static

VOLUME ["/data"]
ENV DIRECTORY_DATA_DIR=/data

EXPOSE 8000

# --proxy-headers : l'adresse reelle du visiteur arrive via Caddy
# (X-Forwarded-For) ; l'anti-bruteforce en depend. "*" est sur ici car le
# port 8000 n'est joignable que par Caddy (reseau interne de compose),
# jamais publie sur la machine.
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
