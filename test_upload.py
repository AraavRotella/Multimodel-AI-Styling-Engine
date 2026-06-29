import requests
from PIL import Image
import io
import os

img = Image.frombytes('RGB', (100, 100), os.urandom(30000))
buf = io.BytesIO()
img.save(buf, format='JPEG')
buf.seek(0)

files = {'file': ('random_test.jpg', buf, 'image/jpeg')}
response = requests.post('http://127.0.0.1:8000/upload-image/', files=files)
print("Status Code:", response.status_code)
print("Response JSON:", response.text)
