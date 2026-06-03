import os
os.environ["SERPER_API_KEY"] = "a2c5c546ad962e1d0ab7d03435da4b3f806a6c30"

from langchain_community.utilities import GoogleSerperAPIWrapper

search = GoogleSerperAPIWrapper()

result = search.run("obama's first name?")

print(result)