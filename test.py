import os

from tavily import TavilyClient

search = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])

result = search.search("obama's first name?", max_results=3)

print(result)
