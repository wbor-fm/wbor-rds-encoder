FROM python:3.12

# Ensure python doesn't buffer logs
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install curl and clean up
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . .

# Download the words.json file from the GitHub repo
RUN curl -L https://raw.githubusercontent.com/zacanger/profane-words/master/words.json -o /app/utils/words.json

# Default command to run the consumer
CMD [ "python", "-u", "rds.py" ]