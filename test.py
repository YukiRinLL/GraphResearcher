import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from langchain_community.utilities import GoogleSerperAPIWrapper

search = GoogleSerperAPIWrapper()

result = search.run("obama's first name?")

print(result)