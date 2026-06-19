key='sk-e37335b652203affa74bfa281d70c986ca3e76eea5e6ddf80559dbb4d483b3bd'


from openai import OpenAI

client = OpenAI(
    base_url="http://168.138.175.149:8080/v1",
    api_key=key
)

response = client.chat.completions.create(
  model="gpt-5.4-pro",
  messages=[
    {"role": "user", "content": "你好?"},

  ],
  timeout=100,

)
# print(response)
print(response.choices[0].message.content)