"""
Simple non-streaming inference example
"""
from openai import OpenAI
import time

client = OpenAI(
    api_key="sxYEtips.xoyFieypSXbMhxi72ZW0en4OiU35idb1",
    base_url="https://inference.baseten.co/v1"
)

# Simple non-streaming call
start = time.time()

response = client.chat.completions.create(
    model="deepseek-ai/DeepSeek-V3.2",
    messages=[
        {"role": "user", "content": "Explain what Python is in 2 sentences."}
    ],
    max_tokens=100,
    temperature=0.7
)

elapsed = time.time() - start

print(response.choices[0].message.content)
print(f"\n[INFO] Response time: {elapsed:.2f}s")
