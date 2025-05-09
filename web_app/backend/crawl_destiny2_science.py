import asyncio
from crawl4ai import AsyncWebCrawler
import json

async def main():
    url = "https://www.destiny2.science"
    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun(url=url)
        # Save markdown output
        with open("destiny2_science_output.md", "w", encoding="utf-8") as f:
            f.write(result.markdown)
        print("Markdown output saved to destiny2_science_output.md")
        # Save JSON output if available and serializable
        json_data = getattr(result, "json", None)
        if json_data and not callable(json_data):
            try:
                with open("destiny2_science_output.json", "w", encoding="utf-8") as f:
                    json.dump(json_data, f, indent=2, ensure_ascii=False)
                print("JSON output saved to destiny2_science_output.json")
            except TypeError as e:
                print(f"Could not save JSON output: {e}")
        else:
            print("No serializable JSON output available from Crawl4AI result.")
        # Print a summary
        print("--- Summary ---")
        print(f"Title: {getattr(result, 'title', 'N/A')}")
        print(f"Number of links: {len(getattr(result, 'links', []))}")
        print(f"Number of tables: {len(getattr(result, 'tables', []))}")
        print(f"Number of headings: {len(getattr(result, 'headings', []))}")

if __name__ == "__main__":
    asyncio.run(main()) 