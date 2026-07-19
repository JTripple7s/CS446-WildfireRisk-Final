FROM python:3.10-slim

WORKDIR /app

# Copy requirements from the predict job folder
COPY wildfire-predict-job/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the pre-trained model folder
COPY model/ /app/model/

# Copy the prediction script
COPY wildfire-predict-job/predict_and_write.py .

CMD ["python", "predict_and_write.py"]
