import requests
import json

api_key = 'AIzaSyDiyy4UUFMqY57wUJYisAXk6dm-M_dbrcE'
url = 'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent'

payload = {
    'systemInstruction': {
        'parts': [{'text': 'You are a teacher.'}],
    },
    'contents': [
        {
            'role': 'user',
            'parts': [{'text': 'Review this code: print("Hello World")'}],
        }
    ],
    'generationConfig': {
        'temperature': 0.2,
        'responseMimeType': 'application/json',
    },
    'safetySettings': [
        {'category': 'HARM_CATEGORY_HARASSMENT', 'threshold': 'BLOCK_NONE'},
        {'category': 'HARM_CATEGORY_HATE_SPEECH', 'threshold': 'BLOCK_NONE'},
        {'category': 'HARM_CATEGORY_SEXUALLY_EXPLICIT', 'threshold': 'BLOCK_NONE'},
        {'category': 'HARM_CATEGORY_DANGEROUS_CONTENT', 'threshold': 'BLOCK_NONE'},
    ],
}

headers = {'x-goog-api-key': api_key}
resp = requests.post(url, json=payload, headers=headers)
print('STATUS:', resp.status_code)
print('RESPONSE:', resp.text)
