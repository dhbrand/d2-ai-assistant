import asyncio
from crawl4ai import AsyncWebCrawler

async def main():
    url = "https://docs.google.com/spreadsheets/d/1JM-0SlxVDAi-C6rGVlLxa-J1WGewEeL8Qvq4htWZHhY/edit#gid=346832350"
    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun(url=url)
        with open("sheet_output.md", "w", encoding="utf-8") as f:
            f.write(result.markdown)
        print("Markdown output saved to sheet_output.md")

if __name__ == "__main__":
    asyncio.run(main())
